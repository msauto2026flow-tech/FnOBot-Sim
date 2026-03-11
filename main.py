"""
main.py — Entry point for the Nifty F&O Bot v5.

Usage:
    python main.py            # Start the bot (normal mode)
    python main.py --login    # Generate fresh Kite access token
    python main.py --brief    # Send manual pre-market briefing

CHANGES (Phase 1 Rank 1):
  run_scan():
    - Fetches India VIX via data.vix_fetcher every scan
    - Fetches next-expiry chain every NEXT_EXPIRY_REFRESH_SCANS scans (~15 min)
    - Computes per-strike Greeks via indicators.greeks_per_strike
    - Logs OI with Greeks via excel_writer.save_oi_with_greeks()
    - Logs futures OHLCV candles via excel_writer.save_futures_candles()
    - Passes VIX + next-expiry data to dashboard generator
    - Uses save_workbook_atomic() — fixes blank Excel file bug

  Scheduler (all TODOs replaced with real calls):
    - 08:45 → pre_market_seed()        : seed RSI/ST/VWAP candles
    - 09:14 → send_pre_market_brief()  : Telegram morning brief
    - 15:30 → run_eod_snapshot()       : EOD capture + Excel finalise + dashboard archive
    - 15:45 → send_post_market_brief() : Telegram post-market brief
    - 19:30 → run_fii_dii_fetch()      : Fetch & save FII/DII data
    - 19:45 → auto_terminate()         : Graceful bot termination
"""

import sys
import time
import datetime
import schedule

from config.settings import (
    IST, SCAN_INTERVAL_MIN, DATA_DIR,
    NEXT_EXPIRY_REFRESH_SCANS,
    PRE_MARKET_SEED_TIME,
    MARKET_OPEN_BRIEF_TIME,
    EOD_SNAPSHOT_TIME,
    POST_MARKET_BRIEF_TIME,
    FII_DII_FETCH_TIME,
    AUTO_TERMINATE_TIME,
)
from core.state import BotState
from core.kite_client import init_kite, generate_access_token
from core.scheduler import is_market_open, setup_graceful_shutdown
from output.telegram import send_telegram, send_heartbeat
from utils.logger import setup_logger, log

# Module-level cache of last complete scan results for post-market brief
_last_scan_results: dict = {}


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN SCAN LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def run_scan(state: BotState):
    """Execute a single market scan cycle."""
    from analysis.option_chain import (
        fetch_option_chain, fetch_next_expiry_chain, analyse_chain,
    )
    from analysis.oi_delta import compute_oi_delta, store_oi_snapshot
    from analysis.support_resistance import compute_sr_levels
    from analysis.signals import generate_signal
    from analysis.futures import fetch_futures, fetch_futures_candles
    from analysis.trade_setup import score_trade_setups
    from indicators.scoring import get_all_scoring_functions
    from indicators import (
        compute_all_vwap, compute_all_technicals,
        compute_all_iv, compute_all_oi_concentration,
    )
    from indicators.greeks_per_strike import compute_greeks_for_chain
    from output.excel_writer import (
        get_daily_filepath, load_or_create_workbook, save_workbook_atomic,
        save_futures_candles, save_oi_with_greeks,
    )
    from Dashboard.dashboard_core import generate_dashboard
    from data.vix_fetcher import fetch_india_vix

    now_ist   = datetime.datetime.now(IST)
    timestamp = now_ist.strftime("%H:%M")
    log.info(f"── Running scan ({timestamp} IST) ──")

    # ── India VIX ─────────────────────────────────────────────────────────────
    vix = fetch_india_vix()
    if vix > 0:
        state.india_vix = vix
        log.info(f"India VIX: {vix:.2f}")

    oi_data       = {}
    analysis_map  = {}
    delta_map     = {}
    signals_map   = {}
    greeks_map    = {}    # {symbol: {strike: {CE: greeks, PE: greeks}}}

    # ── Current expiry option chains ──────────────────────────────────────────
    for symbol in ["NIFTY", "BANKNIFTY"]:
        data = fetch_option_chain(state, symbol)
        if not data:
            log.warning(f"{symbol} — no data")
            continue

        analysis = analyse_chain(data)
        strikes  = sorted(data["chain"].keys())
        atm      = analysis.get("atm", 0)

        # OI delta (3-min, 1-hr, prev-day already in state snapshots)
        delta_data = compute_oi_delta(state, symbol, data["chain"], atm, strikes)
        store_oi_snapshot(state, symbol, data["chain"])

        direction, reasons = generate_signal(
            state, symbol,
            analysis.get("pcr", 0),
            data.get("spot", 0),
            analysis.get("max_pain", 0),
        )

        # Per-strike Greeks using ATM avg_iv from iv_tracker
        # (iv_map computed below — use cached value or default 0.15)
        avg_iv_cached = getattr(state, "_cached_avg_iv", {}).get(symbol, 0.15)
        greeks = compute_greeks_for_chain(
            data["chain"], data["spot"], data["expiry"],
            avg_iv=avg_iv_cached,
            strikes_window=strikes,
        )
        greeks_map[symbol] = greeks

        oi_data[symbol]      = data
        analysis_map[symbol] = analysis
        delta_map[symbol]    = delta_data
        signals_map[symbol]  = (direction, reasons)
        log.info(
            f"{symbol} — Spot: {data['spot']:,.1f}  "
            f"PCR: {analysis.get('pcr', 0)}  Signal: {direction}"
        )

    # ── Next-expiry chains (every 15 min) ─────────────────────────────────────
    should_refresh_next = (state.scan_count % NEXT_EXPIRY_REFRESH_SCANS == 0)
    if should_refresh_next:
        for symbol in list(oi_data.keys()):
            nd = fetch_next_expiry_chain(state, symbol)
            if nd:
                state.next_expiry_data[symbol] = nd
                log.debug(f"{symbol} next expiry refreshed: {nd['expiry']}")

    next_expiry_oi  = state.next_expiry_data
    next_analysis   = {
        sym: analyse_chain(state.next_expiry_data[sym])
        for sym in state.next_expiry_data
        if state.next_expiry_data[sym].get("chain")
    }

    # ── Indicators ───────────────────────────────────────────────────────────
    vwap_map = compute_all_vwap(state.kite, list(oi_data.keys()))
    tech_map = compute_all_technicals(
        state.kite, list(oi_data.keys()),
        seeded_map=state.seeded_candles,
    )
    iv_map   = compute_all_iv(state.kite, oi_data)
    conc_map = compute_all_oi_concentration(oi_data)

    # Cache avg_iv per symbol for next scan's Greeks calc
    if not hasattr(state, "_cached_avg_iv"):
        state._cached_avg_iv = {}
    for sym, iv in iv_map.items():
        if iv and not iv.get("error"):
            state._cached_avg_iv[sym] = iv.get("atm_iv_avg", 15) / 100.0

    # ── Futures + Setup scoring ───────────────────────────────────────────────
    scoring_fns = get_all_scoring_functions()
    futures_map = {}
    sr_map      = {}
    setup_map   = {}

    for symbol in oi_data:
        fut_data = fetch_futures(state, symbol)
        futures_map[symbol] = fut_data
        sr_map[symbol]      = compute_sr_levels(
            state, symbol,
            oi_data[symbol]["chain"],
            oi_data[symbol]["spot"],
            analysis_map[symbol],
        )
        setup_map[symbol] = score_trade_setups(
            symbol, analysis_map[symbol], sr_map[symbol],
            fut_data, delta_map.get(symbol, {}),
            vwap_map.get(symbol, {}), tech_map.get(symbol, {}),
            iv_map.get(symbol, {}), conc_map.get(symbol, {}),
            **scoring_fns,
        )

    # ── Excel logging — FIXED: now uses load_or_create + atomic save ─────────
    last_excel_ts = "—"
    try:
        filepath = get_daily_filepath()
        wb       = load_or_create_workbook(filepath)

        # OI with Greeks
        for symbol in oi_data:
            data     = oi_data[symbol]
            analysis = analysis_map[symbol]
            save_oi_with_greeks(
                wb, symbol, timestamp,
                data.get("expiry", ""),
                data.get("spot", 0),
                analysis.get("atm", 0),
                data.get("chain", {}),
                greeks_map.get(symbol, {}),
            )

        # Futures candles (OBJ 2 — 3-min OHLCV)
        for symbol in futures_map:
            fut  = futures_map[symbol]
            cndl = fetch_futures_candles(state, symbol, fut)
            if cndl:
                save_futures_candles(wb, symbol, fut.get("expiry", ""), cndl)

        # PCR/MaxPain/VIX row
        _log_pcr_vwap_rows(wb, timestamp, oi_data, analysis_map, vwap_map, state.india_vix)

        # OI Delta rows
        _log_oi_delta_rows(wb, timestamp, oi_data, delta_map, state)

        # Technicals + Signals
        _log_technicals_and_signals(wb, timestamp, oi_data, analysis_map, tech_map, signals_map)

        # Futures S/R + Setup
        _log_futures_setup(wb, timestamp, futures_map, sr_map, setup_map)

        save_workbook_atomic(wb, filepath)
        last_excel_ts = timestamp
        log.info(f"[Excel] Saved at {timestamp}")

    except Exception as e:
        log.error(f"Excel logging failed: {e}", exc_info=True)

    # ── Dashboard ─────────────────────────────────────────────────────────────
    try:
        generate_dashboard(
            oi_data_map    = oi_data,
            analysis_map   = analysis_map,
            delta_map      = delta_map,
            signals_map    = signals_map,
            vwap_map       = vwap_map,
            tech_map       = tech_map,
            iv_map         = iv_map,
            conc_map       = conc_map,
            setup_map      = setup_map,
            futures_map    = futures_map,
            sr_map         = sr_map,
            india_vix      = state.india_vix,
            next_expiry_oi = next_expiry_oi,
            next_analysis  = next_analysis,
            scan_count     = state.scan_count,
            last_excel_ts  = last_excel_ts,
            prevday_oi    = state.prevday_oi_snapshot,
        )
    except Exception as e:
        log.error(f"Dashboard generation failed: {e}", exc_info=True)

    # ── Telegram spike alerts ─────────────────────────────────────────────────
    for symbol in oi_data:
        delta  = delta_map.get(symbol, {})
        alerts = delta.get("alerts", [])
        extreme = [a for tier, a in alerts if tier == "EXTREME"]
        if extreme:
            lines = [f"<b>🚨 EXTREME OI SPIKE — {symbol}</b>", ""]
            for a in extreme:
                lines.append(f"  {a['msg']}  (OI: {a['curr_oi']:,})")
            send_telegram("\n".join(lines))

    # Cache last results for post-market brief
    global _last_scan_results
    _last_scan_results = {
        "analysis_map": analysis_map,
        "delta_map":    delta_map,
        "tech_map":     tech_map,
        "iv_map":       iv_map,
        "setup_map":    setup_map,
        "futures_map":  futures_map,
        "vwap_map":     vwap_map,
        "india_vix":    state.india_vix,
        "scan_count":   state.scan_count,
    }

    state.scan_count += 1
    log.info(f"Scan complete — {timestamp} IST (#{state.scan_count})")

    # Heartbeat every 20 scans (≈ 60 min at 3-min intervals)
    if state.scan_count % 20 == 0:
        send_heartbeat(state.scan_count)


# ═══════════════════════════════════════════════════════════════════════════════
#  EXCEL ROW LOGGERS  (extracted from run_scan for clarity)
# ═══════════════════════════════════════════════════════════════════════════════

def _log_pcr_vwap_rows(wb, timestamp, oi_data, analysis_map, vwap_map, india_vix):
    from output.excel_writer import append_row
    ws = wb["PCR_MAXPAIN"]
    for sym in oi_data:
        a  = analysis_map.get(sym, {})
        vd = vwap_map.get(sym, {})
        spot = oi_data[sym].get("spot", 0)
        mp   = a.get("max_pain", 0)
        append_row(ws, [
            timestamp, sym, round(spot, 2),
            a.get("pcr", 0), mp,
            round((spot - mp) / mp * 100, 2) if mp else 0,
            a.get("total_ce", 0), a.get("total_pe", 0),
            round(india_vix, 2),
            vd.get("vwap", 0),           vd.get("band1_upper", 0),
            vd.get("band1_lower", 0),    vd.get("band2_upper", 0),
            vd.get("band2_lower", 0),    vd.get("weekly_avwap", 0),
            vd.get("vwap_slope", 0),     vd.get("vwap_position", "—"),
        ])


def _log_oi_delta_rows(wb, timestamp, oi_data, delta_map, state):
    from output.excel_writer import append_row
    ws = wb["OI_DELTA"]
    for sym in oi_data:
        delta = delta_map.get(sym, {})
        if not delta:
            continue
        mood = delta.get("mood", "—")
        hr_snap  = state.hour_oi_snapshot.get(sym, {})
        pd_snap  = state.prevday_oi_snapshot.get(sym, {})
        chain    = oi_data[sym].get("chain", {})
        for d in delta.get("deltas", []):
            s      = d["Strike"]
            ce_cur = chain.get(s, {}).get("CE", {}).get("openInterest", 0)
            pe_cur = chain.get(s, {}).get("PE", {}).get("openInterest", 0)
            ce_1h  = hr_snap.get(s, {}).get("CE", ce_cur)
            pe_1h  = hr_snap.get(s, {}).get("PE", pe_cur)
            ce_pd  = pd_snap.get(s, {}).get("CE", ce_cur)
            pe_pd  = pd_snap.get(s, {}).get("PE", pe_cur)
            append_row(ws, [
                timestamp, sym, int(s),
                d["CE_prev"], d["CE_curr"], d["CE_delta"], d["CE_pct"],
                ce_cur - ce_1h,
                round((ce_cur - ce_1h) / ce_1h * 100, 1) if ce_1h else 0,
                ce_cur - ce_pd,
                round((ce_cur - ce_pd) / ce_pd * 100, 1) if ce_pd else 0,
                d["PE_prev"], d["PE_curr"], d["PE_delta"], d["PE_pct"],
                pe_cur - pe_1h,
                round((pe_cur - pe_1h) / pe_1h * 100, 1) if pe_1h else 0,
                pe_cur - pe_pd,
                round((pe_cur - pe_pd) / pe_pd * 100, 1) if pe_pd else 0,
                mood,
            ])


def _log_technicals_and_signals(wb, timestamp, oi_data, analysis_map, tech_map, signals_map):
    from output.excel_writer import append_row
    ws_tech = wb["TECHNICALS"]
    ws_sig  = wb["SIGNALS"]   
    for sym in oi_data:
        td  = tech_map.get(sym, {})
        a   = analysis_map.get(sym, {})
        sig, reasons = signals_map.get(sym, ("—", []))
        if td and not td.get("error"):
            from indicators.technicals import get_technicals_excel_values
            append_row(ws_tech, get_technicals_excel_values(td, sym, timestamp))
        spot = oi_data[sym].get("spot", 0)
        append_row(ws_sig, [
            timestamp, sym, round(spot, 2),
            a.get("pcr", 0), a.get("max_pain", 0), sig,
            reasons[0] if len(reasons) > 0 else "",
            reasons[1] if len(reasons) > 1 else "",
            reasons[2] if len(reasons) > 2 else "",
        ])


def _log_futures_setup(wb, timestamp, futures_map, sr_map, setup_map):
    from output.excel_writer import append_row
    ws = wb["FUTURES"]
    for sym in futures_map:
        fut   = futures_map[sym]
        sr    = sr_map.get(sym, {})
        setup = setup_map.get(sym, {})
        res   = sr.get("resistance", [])
        sup   = sr.get("support",    [])
        scores = setup.get("scores", {})
        append_row(ws, [
            timestamp, sym,
            fut.get("contract", ""), fut.get("expiry", ""), fut.get("days_left", 0),
            fut.get("ltp", 0), fut.get("spot", 0),
            fut.get("basis", 0), fut.get("basis_pct", 0),
            res[0]["level"] if len(res) > 0 else "",
            res[1]["level"] if len(res) > 1 else "",
            res[2]["level"] if len(res) > 2 else "",
            sup[0]["level"] if len(sup) > 0 else "",
            sup[1]["level"] if len(sup) > 1 else "",
            sup[2]["level"] if len(sup) > 2 else "",
            setup.get("best_label", ""),
            scores.get("long_ce", 0), scores.get("long_pe", 0),
            scores.get("short_straddle", 0), scores.get("short_strangle", 0),
        ])


# ═══════════════════════════════════════════════════════════════════════════════
#  SCHEDULED TASKS
# ═══════════════════════════════════════════════════════════════════════════════

def scheduled_scan(state: BotState):
    """Run scan only during market hours."""
    if is_market_open():
        try:
            run_scan(state)
        except Exception as e:
            log.error(f"Scan failed: {e}", exc_info=True)
            send_telegram(f"⚠️ <b>Scan error:</b> {e}")
    else:
        t = datetime.datetime.now(IST).strftime("%H:%M")
        log.debug(f"[{t} IST] Market closed — waiting.")


def pre_market_seed(state: BotState):
    """08:45 IST — fetch historical candles to seed RSI, Supertrend, VWAP."""
    log.info("═══ Pre-market seed starting (08:45 IST) ═══")
    try:
        from indicators.technicals import seed_technicals_premarket
        seeded = seed_technicals_premarket(state.kite)
        state.seeded_candles.update(seeded)
        log.info(f"Pre-market seed complete: {list(seeded.keys())}")
        send_telegram(
            "🌱 <b>Pre-market seed complete</b> — RSI & Supertrend data loaded.\n"
            "Market opens at 09:15 IST."
        )
    except Exception as e:
        log.error(f"Pre-market seed failed: {e}", exc_info=True)


def send_pre_market_brief(state: BotState):
    """09:14 IST — send morning brief to Telegram."""
    log.info("═══ Sending pre-market brief (09:14 IST) ═══")
    try:
        from indicators import compute_all_technicals, compute_all_vwap, compute_all_iv
        from output.message_builder import build_pre_market_brief
        from data.vix_fetcher import fetch_india_vix
        import yfinance as yf

        # Fetch global markets
        global_markets = {}
        try:
            from config.settings import GLOBAL_TICKERS
            for name, ticker in GLOBAL_TICKERS.items():
                try:
                    t    = yf.Ticker(ticker)
                    hist = t.history(period="2d")
                    if len(hist) >= 2:
                        pct = (hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100
                        global_markets[name] = round(pct, 2)
                except Exception:
                    pass
        except ImportError:
            pass

        vix      = fetch_india_vix()
        tech_map = compute_all_technicals(state.kite, ["NIFTY", "BANKNIFTY"],
                                          seeded_map=state.seeded_candles)
        vwap_map = compute_all_vwap(state.kite, ["NIFTY", "BANKNIFTY"])
        iv_map   = {}   # no chain data yet

        msg = build_pre_market_brief(global_markets, 0, vix, tech_map, vwap_map, iv_map)
        send_telegram(msg)
        log.info("Pre-market brief sent.")
    except Exception as e:
        log.error(f"Pre-market brief failed: {e}", exc_info=True)
        send_telegram(f"⚠️ Pre-market brief error: {e}")


def run_eod_snapshot(state: BotState):
    """15:30 IST — EOD data capture, Excel finalise, dashboard archive."""
    log.info("═══ EOD Snapshot (15:30 IST) ═══")
    try:
        from output.excel_writer import get_daily_filepath, load_or_create_workbook, save_workbook_atomic
        from Dashboard.dashboard_core import archive_dashboard

        # Archive the dashboard
        archive_dashboard()
        log.info("[EOD] Dashboard archived.")

        # Mark eod_captured so FII/DII knows the day is done
        state.eod_captured = True

        # Final Excel save (touch the file to ensure it exists even if no data was written)
        filepath = get_daily_filepath()
        wb       = load_or_create_workbook(filepath)
        save_workbook_atomic(wb, filepath)
        log.info(f"[EOD] Excel finalised: {filepath}")

        send_telegram(
            f"📊 <b>EOD Snapshot complete — {datetime.date.today()}</b>\n"
            f"Dashboard archived. FII/DII data expected at 19:30 IST."
        )
    except Exception as e:
        log.error(f"EOD snapshot failed: {e}", exc_info=True)


def send_post_market_brief(state: BotState):
    """15:45 IST — send post-market Telegram brief."""
    log.info("═══ Sending post-market brief (15:45 IST) ═══")
    try:
        from output.message_builder import build_post_market_brief
        r   = _last_scan_results
        msg = build_post_market_brief(
            analysis_map = r.get("analysis_map", {}),
            delta_map    = r.get("delta_map",    {}),
            tech_map     = r.get("tech_map",     {}),
            iv_map       = r.get("iv_map",       {}),
            setup_map    = r.get("setup_map",    {}),
            futures_map  = r.get("futures_map",  {}),
            vwap_map     = r.get("vwap_map",     {}),
            india_vix    = r.get("india_vix",    0.0),
            scan_count   = r.get("scan_count",   0),
            fii_dii      = None,  # not yet available; comes at 19:30
        )
        send_telegram(msg)
        log.info("Post-market brief sent.")
    except Exception as e:
        log.error(f"Post-market brief failed: {e}", exc_info=True)


def run_fii_dii_fetch(state: BotState):
    """19:30 IST — fetch FII/DII data and save to Excel."""
    log.info("═══ FII/DII Fetch (19:30 IST) ═══")
    try:
        from data.fii_dii import fetch_fii_dii
        from output.excel_writer import get_daily_filepath, load_or_create_workbook, save_workbook_atomic
        from output.excel_writer import save_fii_dii
        from output.message_builder import build_fii_dii_brief

        fii_dii  = fetch_fii_dii()
        filepath = get_daily_filepath()
        wb       = load_or_create_workbook(filepath)
        save_fii_dii(wb, fii_dii)
        save_workbook_atomic(wb, filepath)

        msg = build_fii_dii_brief(fii_dii)
        send_telegram(msg)
        log.info("[FII/DII] Saved and brief sent.")
    except Exception as e:
        log.error(f"FII/DII fetch failed: {e}", exc_info=True)
        send_telegram(f"⚠️ FII/DII fetch error: {e}")


def auto_terminate(state: BotState):
    """19:45 IST — gracefully terminate the bot."""
    log.info("═══ Auto-terminate (19:45 IST) ═══")
    send_telegram("🔴 <b>Bot auto-terminating</b> — all tasks complete for today. Good night! 🌙")
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    setup_logger("fnobot", log_dir=DATA_DIR / "logs")

    log.info("=" * 62)
    log.info("  Nifty & BankNifty F&O Bot — v5 (Phase 1 Rank 1 Update)")
    log.info("=" * 62)

    state = BotState()

    # CLI modes
    if len(sys.argv) > 1:
        if sys.argv[1] == "--login":
            generate_access_token()
            return
        if sys.argv[1] == "--brief":
            if not init_kite(state):
                log.error("Cannot send brief — Kite not initialised.")
                sys.exit(1)
            send_pre_market_brief(state)
            return

    # Init Kite
    if not init_kite(state):
        log.error("Cannot start — Kite not initialised. Run: python main.py --login")
        sys.exit(1)

    # Graceful shutdown
    setup_graceful_shutdown(state, send_telegram)

    # ── Wire all schedules ────────────────────────────────────────────────────
    schedule.every().day.at(PRE_MARKET_SEED_TIME).do(
        pre_market_seed, state=state
    )
    schedule.every().day.at(MARKET_OPEN_BRIEF_TIME).do(
        send_pre_market_brief, state=state
    )
    schedule.every(SCAN_INTERVAL_MIN).minutes.do(
        scheduled_scan, state=state
    )
    schedule.every().day.at(EOD_SNAPSHOT_TIME).do(
        run_eod_snapshot, state=state
    )
    schedule.every().day.at(POST_MARKET_BRIEF_TIME).do(
        send_post_market_brief, state=state
    )
    schedule.every().day.at(FII_DII_FETCH_TIME).do(
        run_fii_dii_fetch, state=state
    )
    schedule.every().day.at(AUTO_TERMINATE_TIME).do(
        auto_terminate, state=state
    )

    log.info(
        f"Scheduler active — scanning every {SCAN_INTERVAL_MIN} min during market hours.\n"
        f"  Seed: {PRE_MARKET_SEED_TIME} | Brief: {MARKET_OPEN_BRIEF_TIME} | "
        f"EOD: {EOD_SNAPSHOT_TIME} | Post: {POST_MARKET_BRIEF_TIME} | "
        f"FII/DII: {FII_DII_FETCH_TIME} | Terminate: {AUTO_TERMINATE_TIME}"
    )

    # Run immediate scan if market is open at startup
    if is_market_open():
        run_scan(state)
    else:
        log.info("Market currently closed — waiting.")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
