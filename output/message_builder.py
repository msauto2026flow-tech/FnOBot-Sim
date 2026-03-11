"""
output/message_builder.py — Telegram message formatting.

CHANGES (Phase 1 Rank 1 — Comment "Create a Post Market Brief"):
  - build_post_market_brief() — NEW: 15:45 IST post-market summary
  - build_pre_market_brief()  — existing (unchanged interface)
  - format_eod_summary()      — NEW helper used by post-market brief
"""

import datetime
from config.settings import IST
from utils.logger import log


# ═══════════════════════════════════════════════════════════════════════════════
#  PRE-MARKET BRIEF (existing — interface unchanged)
# ═══════════════════════════════════════════════════════════════════════════════

def build_pre_market_brief(
    global_markets: dict,
    gift_nifty: float,
    india_vix: float,
    tech_map: dict,
    vwap_map: dict,
    iv_map: dict,
) -> str:
    """
    Build the pre-market Telegram brief sent at 09:14 IST.
    Returns formatted HTML string.
    """
    now_ist   = datetime.datetime.now(IST)
    date_str  = now_ist.strftime("%d %b %Y")
    lines     = [f"🌅 <b>Pre-Market Brief — {date_str}</b>", ""]

    # Global markets
    if global_markets:
        lines.append("🌍 <b>Global Markets</b>")
        for name, chg in global_markets.items():
            if chg is None:
                continue
            e = "🟢" if chg >= 0 else "🔴"
            lines.append(f"  {e} {name}: <b>{chg:+.2f}%</b>")
        lines.append("")

    # Gift Nifty + VIX
    if gift_nifty:
        lines.append(f"🎁 Gift Nifty: <b>{gift_nifty:,.1f}</b>")
    if india_vix > 0:
        vix_e = "😰" if india_vix > 20 else "😌" if india_vix < 14 else "😐"
        lines.append(f"{vix_e} India VIX: <b>{india_vix:.2f}</b>")
    lines.append("")

    # Technicals per symbol
    for sym in ["NIFTY", "BANKNIFTY"]:
        td = tech_map.get(sym)
        vd = vwap_map.get(sym)
        iv = iv_map.get(sym)
        lines.append(f"📊 <b>{sym}</b>")
        if td and not td.get("error"):
            from indicators.technicals import format_technicals_premarket_line
            lines.append(format_technicals_premarket_line(td, sym))
        if vd and not vd.get("error"):
            from indicators.vwap import format_vwap_premarket_line
            lines.append(format_vwap_premarket_line(vd, sym))
        if iv and not iv.get("error"):
            from indicators.iv_tracker import format_iv_premarket_line
            lines.append(format_iv_premarket_line(iv, sym))
        lines.append("")

    lines.append("🔔 Market opens at 09:15 IST. Good luck! 🎯")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  POST-MARKET BRIEF (NEW — sent at 15:45 IST)
# ═══════════════════════════════════════════════════════════════════════════════

def build_post_market_brief(
    analysis_map: dict,       # {symbol: analyse_chain() result}
    delta_map:    dict,       # {symbol: compute_oi_delta() result}
    tech_map:     dict,       # {symbol: compute_technicals() result}
    iv_map:       dict,       # {symbol: compute_iv() result}
    setup_map:    dict,       # {symbol: score_trade_setups() result}
    futures_map:  dict,       # {symbol: fetch_futures() result}
    vwap_map:     dict,       # {symbol: compute_vwap() result}
    india_vix:    float = 0.0,
    scan_count:   int   = 0,
    fii_dii:      dict  = None,
) -> str:
    """
    Build the post-market Telegram brief sent at 15:45 IST.
    Summarises the full trading day: final OI stance, signals, technicals,
    top setup score, VIX, and FII/DII if available.
    Returns formatted HTML string.
    """
    now_ist  = datetime.datetime.now(IST)
    date_str = now_ist.strftime("%d %b %Y")
    lines    = [
        f"🔔 <b>Post-Market Brief — {date_str}</b>",
        f"<i>Market closed · {scan_count} scans completed today</i>",
        "",
    ]

    # India VIX
    if india_vix > 0:
        vix_e = "😰" if india_vix > 20 else "😌" if india_vix < 14 else "😐"
        lines.append(f"{vix_e} India VIX close: <b>{india_vix:.2f}</b>")
        lines.append("")

    # Per-symbol summary
    for sym in ["NIFTY", "BANKNIFTY"]:
        analysis = analysis_map.get(sym, {})
        delta    = delta_map.get(sym, {})
        td       = tech_map.get(sym)
        iv       = iv_map.get(sym)
        setup    = setup_map.get(sym, {})
        fut      = futures_map.get(sym, {})
        vwap     = vwap_map.get(sym)

        spot     = analysis.get("spot", fut.get("spot", 0))
        pcr      = analysis.get("pcr", 0)
        max_pain = analysis.get("max_pain", 0)
        mood     = delta.get("mood", "—")

        lines.append(f"━━━━━━━━━━━━━━━━━━")
        lines.append(f"📌 <b>{sym}</b>  Spot: <b>{spot:,.1f}</b>")
        lines.append(f"  PCR: <b>{pcr:.3f}</b>  Max Pain: <b>{max_pain:,.0f}</b>")
        lines.append(f"  OI Mood: {mood}")

        if fut:
            basis = fut.get("basis", 0)
            b_e   = "🟢" if basis > 0 else "🔴"
            lines.append(f"  {b_e} Futures: {fut.get('ltp', 0):,.1f}  Basis: {basis:+.0f}")

        if td and not td.get("error"):
            st  = td.get("supertrend", "—")
            rsi = td.get("rsi", 0)
            hhl = td.get("hh_ll", "—")
            st_e = "🟢" if st == "UP" else "🔴"
            lines.append(f"  {st_e} ST:{st}  RSI:{rsi:.1f}  Struct:{hhl}")

        if vwap and not vwap.get("error"):
            pos = vwap.get("vwap_position", "—")
            vwap_val = vwap.get("vwap", 0)
            lines.append(f"  VWAP: {vwap_val:,.1f} ({pos})")

        if iv and not iv.get("error"):
            lines.append(
                f"  IV: CE {iv.get('atm_ce_iv',0):.1f}%  PE {iv.get('atm_pe_iv',0):.1f}%  "
                f"Straddle {iv.get('straddle_pts',0):.0f} pts  [{iv.get('iv_rank','—')}]"
            )

        if setup:
            best  = setup.get("best_label", "—")
            score = setup.get("best_score", 0)
            lines.append(f"  🎯 Best Setup: <b>{best}</b> ({score}/10)")

        lines.append("")

    # FII/DII (if already fetched — may be None at 15:45, arrives at 19:30)
    if fii_dii and not fii_dii.get("error"):
        from data.fii_dii import build_fii_dii_telegram
        lines.append(build_fii_dii_telegram(fii_dii))
        lines.append("")
    else:
        lines.append("📊 <i>FII/DII data expected at 19:30 IST</i>")
        lines.append("")

    lines.append("📁 Check MarketData Excel + dashboard for full details.")
    lines.append("💤 Bot will fetch FII/DII at 19:30 and terminate at 19:45.")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  FII/DII BRIEF (sent at 19:30 after fetch)
# ═══════════════════════════════════════════════════════════════════════════════

def build_fii_dii_brief(fii_dii: dict) -> str:
    """Compact Telegram message after 19:30 FII/DII fetch."""
    if not fii_dii or fii_dii.get("error"):
        return "📊 <b>FII/DII:</b> Could not fetch today's data. Please check NSE manually."
    from data.fii_dii import build_fii_dii_telegram
    return build_fii_dii_telegram(fii_dii) + "\n\n🔴 Bot terminating now."
