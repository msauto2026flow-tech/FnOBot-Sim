"""
indicators/technicals.py — Supertrend, EMA20, RSI14, HH/LL structure.

Phase 1 Rank 1:
  - compute_technicals() fetches 15-min candles (seeds from previous sessions for RSI warmup)
  - seed_technicals_premarket() called at 08:45 to pre-load historical candles
  - HH/LL classification retains the structure required by trade_setup.py
"""

import datetime

from config.settings import (
    IST, INDEX_TOKENS,
    ST_PERIOD, ST_MULTIPLIER,
    EMA_PERIOD, RSI_PERIOD,
    DIV_LOOKBACK, HHLH_LOOKBACK,
)
from utils.logger import log


# ═══════════════════════════════════════════════════════════════════════════════
#  CANDLE FETCHING
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_15m_candles(kite, symbol: str, days_back: int = 5) -> list:
    """
    Fetch 15-min index candles going back 'days_back' calendar days.
    Fetching prior sessions ensures RSI and Supertrend are properly seeded
    from the very first market-hours scan.
    """
    token = INDEX_TOKENS.get(symbol)
    if not token:
        return []
    try:
        now_ist    = datetime.datetime.now(IST)
        fetch_to   = now_ist.replace(tzinfo=None)
        fetch_from = (now_ist - datetime.timedelta(days=days_back)).replace(
            hour=9, minute=0, second=0, microsecond=0, tzinfo=None
        )
        candles = kite.historical_data(
            instrument_token=token,
            from_date=fetch_from,
            to_date=fetch_to,
            interval="15minute",
        )
        return candles or []
    except Exception as e:
        log.warning(f"[Technicals] {symbol} candle fetch error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERNAL CALCULATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_atr(candles: list, period: int) -> list:
    """Compute True Range and Wilder-smoothed ATR for each candle."""
    trs = []
    for i, c in enumerate(candles):
        if i == 0:
            tr = c["high"] - c["low"]
        else:
            prev_close = candles[i - 1]["close"]
            tr = max(
                c["high"] - c["low"],
                abs(c["high"] - prev_close),
                abs(c["low"]  - prev_close),
            )
        trs.append(tr)

    atrs = [0.0] * len(trs)
    if len(trs) < period:
        return atrs

    atrs[period - 1] = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atrs[i] = (atrs[i - 1] * (period - 1) + trs[i]) / period
    return atrs


def _compute_supertrend(candles: list, period: int, multiplier: float) -> list:
    """
    Compute Supertrend for each candle.
    Returns list of dicts: {direction: 'UP'|'DOWN', level: float, atr: float}
    """
    atrs = _compute_atr(candles, period)
    n    = len(candles)

    upper_band = [0.0] * n
    lower_band = [0.0] * n
    supertrend = [0.0] * n
    direction  = ["UP"] * n

    for i in range(period - 1, n):
        hl2 = (candles[i]["high"] + candles[i]["low"]) / 2.0
        atr = atrs[i]
        ub  = hl2 + multiplier * atr
        lb  = hl2 - multiplier * atr

        if i == period - 1:
            upper_band[i] = ub
            lower_band[i] = lb
            supertrend[i] = ub
            direction[i]  = "DOWN"
        else:
            prev_ub    = upper_band[i - 1]
            prev_lb    = lower_band[i - 1]
            prev_close = candles[i - 1]["close"]

            upper_band[i] = ub if ub < prev_ub or prev_close > prev_ub else prev_ub
            lower_band[i] = lb if lb > prev_lb or prev_close < prev_lb else prev_lb

            if direction[i - 1] == "UP":
                if candles[i]["close"] < lower_band[i]:
                    direction[i]  = "DOWN"
                    supertrend[i] = upper_band[i]
                else:
                    direction[i]  = "UP"
                    supertrend[i] = lower_band[i]
            else:
                if candles[i]["close"] > upper_band[i]:
                    direction[i]  = "UP"
                    supertrend[i] = lower_band[i]
                else:
                    direction[i]  = "DOWN"
                    supertrend[i] = upper_band[i]

    return [
        {"direction": direction[i], "level": round(supertrend[i], 2), "atr": round(atrs[i], 2)}
        for i in range(n)
    ]


def _compute_ema(prices: list, period: int) -> list:
    """EMA — returns list same length as prices; leading values are 0."""
    if len(prices) < period:
        return [0.0] * len(prices)
    ema = [0.0] * len(prices)
    k   = 2.0 / (period + 1)
    ema[period - 1] = sum(prices[:period]) / period
    for i in range(period, len(prices)):
        ema[i] = prices[i] * k + ema[i - 1] * (1 - k)
    return ema


def _compute_rsi(closes: list, period: int) -> list:
    """Wilder-smoothed RSI — returns list same length as closes."""
    n          = len(closes)
    rsi_values = [0.0] * n
    if n < period + 1:
        return rsi_values

    gains  = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        diff    = closes[i] - closes[i - 1]
        gains[i]  = max(diff, 0.0)
        losses[i] = max(-diff, 0.0)

    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period

    if avg_loss == 0:
        rsi_values[period] = 100.0
    else:
        rsi_values[period] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_values[i] = 100.0
        else:
            rsi_values[i] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    return rsi_values


def _rsi_zone(rsi: float) -> str:
    if rsi >= 70:  return "OVERBOUGHT"
    if rsi >= 60:  return "BULLISH"
    if rsi >= 45:  return "NEUTRAL"
    if rsi >= 30:  return "BEARISH"
    return "OVERSOLD"


def _detect_rsi_divergence(candles: list, rsi_values: list, lookback: int) -> str | None:
    """Detect bullish/bearish RSI divergence from recent valid candles."""
    valid = [(i, candles[i]["close"], rsi_values[i])
             for i in range(len(candles)) if rsi_values[i] > 0]
    if len(valid) < lookback * 2:
        return None
    recent  = valid[-lookback:]
    price_a, rsi_a = recent[0][1], recent[0][2]
    price_b, rsi_b = recent[-1][1], recent[-1][2]
    if price_b < price_a and rsi_b > rsi_a:
        return "BULLISH_DIV"
    if price_b > price_a and rsi_b < rsi_a:
        return "BEARISH_DIV"
    return None


def _classify_hh_ll(candles: list, lookback: int) -> tuple:
    """Classify last 'lookback' candles as HH/HL, LH/LL, or RANGING."""
    n = len(candles)
    if n < lookback:
        return "INSUFFICIENT_DATA", f"Need {lookback}, have {n}"
    recent = candles[-lookback:]
    highs  = [c["high"] for c in recent]
    lows   = [c["low"]  for c in recent]
    hh = all(highs[i] > highs[i - 1] for i in range(1, len(highs)))
    hl = all(lows[i]  > lows[i - 1]  for i in range(1, len(lows)))
    lh = all(highs[i] < highs[i - 1] for i in range(1, len(highs)))
    ll = all(lows[i]  < lows[i - 1]  for i in range(1, len(lows)))
    if hh and hl:
        return "HH/HL", f"Uptrend: rising highs and lows over last {lookback} candles"
    if lh and ll:
        return "LH/LL", f"Downtrend: falling highs and lows over last {lookback} candles"
    if hh:
        return "HH/—", f"Higher highs but mixed lows"
    if ll:
        return "—/LL", f"Lower lows but mixed highs"
    return "RANGING", f"No clear structure over last {lookback} candles"


# ═══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def seed_technicals_premarket(kite, symbols=None) -> dict:
    """
    Pre-market seeding — call at 08:45 IST.
    Fetches 7 calendar days of 15-min candles so RSI and Supertrend are
    fully warmed-up by the first 09:15 scan.
    Returns {symbol: candle_list} for storage in BotState.
    """
    if symbols is None:
        symbols = ["NIFTY", "BANKNIFTY"]
    seeded = {}
    for sym in symbols:
        candles = _fetch_15m_candles(kite, sym, days_back=7)
        seeded[sym] = candles
        log.info(f"[Technicals] {sym} pre-market seed: {len(candles)} candles loaded")
    return seeded


def compute_technicals(kite, symbol: str, seeded_candles: list = None) -> dict:
    """
    Compute Supertrend, EMA20, RSI14, RSI divergence, and HH/LL.

    Args:
        kite:           KiteConnect instance
        symbol:         "NIFTY" or "BANKNIFTY"
        seeded_candles: Pre-loaded candle list from seed_technicals_premarket().
                        If None, falls back to a live fetch (5 days).
    """
    if kite is None:
        return {"error": "Kite not initialised"}

    candles = seeded_candles if seeded_candles else _fetch_15m_candles(kite, symbol, days_back=5)
    if not candles or len(candles) < RSI_PERIOD + 2:
        return {"error": f"Insufficient candles: {len(candles) if candles else 0}"}

    closes = [c["close"] for c in candles]
    n      = len(candles)

    # Supertrend
    st_results = _compute_supertrend(candles, ST_PERIOD, ST_MULTIPLIER)
    last_st    = st_results[-1]
    supertrend = last_st.get("direction", "UP")
    st_level   = last_st.get("level", 0.0)
    st_atr     = last_st.get("atr", 0.0)

    # EMA20
    ema_series     = _compute_ema(closes, EMA_PERIOD)
    ema20          = round(ema_series[-1], 2)
    spot           = closes[-1]
    ema20_distance = round(spot - ema20, 2)
    ema20_dist_pct = round(ema20_distance / ema20 * 100, 2) if ema20 else 0.0
    if ema20_dist_pct > 0.1:    ema20_relation = "ABOVE"
    elif ema20_dist_pct < -0.1: ema20_relation = "BELOW"
    else:                        ema20_relation = "AT"

    # RSI
    rsi_series = _compute_rsi(closes, RSI_PERIOD)
    rsi        = round(rsi_series[-1], 1)
    rsi_z      = _rsi_zone(rsi)
    divergence = _detect_rsi_divergence(candles, rsi_series, DIV_LOOKBACK)

    # HH/LL
    hh_ll, hh_ll_detail = _classify_hh_ll(candles, HHLH_LOOKBACK)

    return {
        "supertrend":         supertrend,
        "supertrend_level":   st_level,
        "supertrend_atr":     st_atr,
        "ema20":              ema20,
        "ema20_distance":     ema20_distance,
        "ema20_distance_pct": ema20_dist_pct,
        "ema20_relation":     ema20_relation,
        "rsi":                rsi,
        "rsi_zone":           rsi_z,
        "rsi_divergence":     divergence,
        "hh_ll":              hh_ll,
        "hh_ll_detail":       hh_ll_detail,
        "candles_15m":        n,
        "as_of":              str(candles[-1]["date"]),
        "error":              None,
    }


def compute_all_technicals(kite, symbols=None, seeded_map: dict = None) -> dict:
    """Compute technicals for all symbols. seeded_map: {symbol: [candles]}."""
    if symbols is None:
        symbols = ["NIFTY", "BANKNIFTY"]
    result = {}
    for sym in symbols:
        seeded = (seeded_map or {}).get(sym)
        td = compute_technicals(kite, sym, seeded_candles=seeded)
        result[sym] = td
        if td and not td.get("error"):
            log.info(
                f"[Tech] {sym} ST:{td['supertrend']}@{td['supertrend_level']:,.0f}  "
                f"RSI:{td['rsi']}[{td['rsi_zone']}]  EMA:{td['ema20_relation']}  HH/LL:{td['hh_ll']}"
            )
        else:
            log.warning(f"[Tech] {sym}: {td.get('error', 'unavailable') if td else 'no data'}")
    return result


def score_technicals(td: dict) -> dict:
    """Translate technicals into setup score contributions."""
    scores   = {"long_ce": 0, "long_pe": 0, "short_straddle": 0, "short_strangle": 0}
    notes    = []
    override = "NONE"

    if not td or td.get("error"):
        return {**scores, "supertrend_override": override, "notes": ["Technicals unavailable"]}

    st      = td.get("supertrend", "UP")
    rsi     = td.get("rsi", 50.0)
    rsi_z   = td.get("rsi_zone", "NEUTRAL")
    hh_ll   = td.get("hh_ll", "RANGING")
    ema_rel = td.get("ema20_relation", "AT")
    div     = td.get("rsi_divergence")

    # Supertrend — hard override
    if st == "UP":
        scores["long_ce"] += 2
        scores["short_strangle"] += 1
        override = "BULLISH_FILTER"
        notes.append("Supertrend UP → bullish bias")
    else:
        scores["long_pe"] += 2
        scores["short_strangle"] += 1
        override = "BEARISH_FILTER"
        notes.append("Supertrend DOWN → bearish bias")

    # RSI
    if rsi_z == "OVERBOUGHT":
        scores["long_pe"] += 2; scores["short_straddle"] += 1
        notes.append(f"RSI {rsi} overbought")
    elif rsi_z == "OVERSOLD":
        scores["long_ce"] += 2; scores["short_straddle"] += 1
        notes.append(f"RSI {rsi} oversold")
    elif rsi_z == "BULLISH":
        scores["long_ce"] += 1
        notes.append(f"RSI {rsi} bullish zone")
    elif rsi_z == "BEARISH":
        scores["long_pe"] += 1
        notes.append(f"RSI {rsi} bearish zone")
    else:
        scores["short_straddle"] += 1

    # RSI divergence
    if div == "BULLISH_DIV":
        scores["long_ce"] += 2; notes.append("RSI bullish divergence")
    elif div == "BEARISH_DIV":
        scores["long_pe"] += 2; notes.append("RSI bearish divergence")

    # EMA20 position
    if ema_rel == "ABOVE":
        scores["long_ce"] += 1; notes.append("Price above EMA20")
    elif ema_rel == "BELOW":
        scores["long_pe"] += 1; notes.append("Price below EMA20")
    else:
        scores["short_straddle"] += 1

    # HH/LL structure
    if "HH" in hh_ll and "HL" in hh_ll:
        scores["long_ce"] += 1; notes.append("HH/HL uptrend structure")
    elif "LH" in hh_ll and "LL" in hh_ll:
        scores["long_pe"] += 1; notes.append("LH/LL downtrend structure")
    else:
        scores["short_straddle"] += 1

    return {**scores, "supertrend_override": override, "notes": notes}


# ── Excel / Telegram / HTML helpers ──────────────────────────────────────────

def get_technicals_excel_headers():
    return [
        "Timestamp", "Symbol",
        "Supertrend", "Supertrend_Level", "Supertrend_ATR",
        "EMA20", "EMA20_Distance", "EMA20_Distance_Pct", "EMA20_Relation",
        "RSI", "RSI_Zone", "RSI_Divergence",
        "HH_LL", "HH_LL_Detail", "Candles_15m", "As_Of",
    ]


def get_technicals_excel_values(td, symbol, timestamp):
    if not td or td.get("error"):
        return [timestamp, symbol] + ["—"] * 14
    return [
        timestamp, symbol,
        td.get("supertrend", "—"), td.get("supertrend_level", 0), td.get("supertrend_atr", 0),
        td.get("ema20", 0), td.get("ema20_distance", 0), td.get("ema20_distance_pct", 0),
        td.get("ema20_relation", "—"),
        td.get("rsi", 0), td.get("rsi_zone", "—"),
        td.get("rsi_divergence") or "None",
        td.get("hh_ll", "—"), td.get("hh_ll_detail", "—"),
        td.get("candles_15m", 0), td.get("as_of", "—"),
    ]


def format_technicals_telegram_line(td, symbol):
    if not td or td.get("error"):
        return f"[{symbol}] Technicals: unavailable"
    st_e = "🟢" if td.get("supertrend") == "UP" else "🔴"
    return (
        f"{st_e} {symbol}  ST:{td.get('supertrend','—')}@{td.get('supertrend_level',0):,.0f}  "
        f"RSI:{td.get('rsi',0)}[{td.get('rsi_zone','—')}]  "
        f"EMA:{td.get('ema20_relation','—')}  Struct:{td.get('hh_ll','—')}"
    )


def format_technicals_premarket_line(td, symbol):
    if not td or td.get("error"):
        return f"  {symbol} Technicals: awaiting market open"
    return (
        f"  {symbol}: Supertrend <b>{td.get('supertrend','—')}</b>  "
        f"RSI <b>{td.get('rsi',0)}</b>  HH/LL <b>{td.get('hh_ll','—')}</b>"
    )


def build_technicals_html(td, symbol):
    if not td or td.get("error"):
        return ""
    st      = td.get("supertrend", "UP")
    rsi     = td.get("rsi", 50.0)
    hh_ll   = td.get("hh_ll", "—")
    ema_rel = td.get("ema20_relation", "AT")
    ema20   = td.get("ema20", 0)
    div     = td.get("rsi_divergence") or "None"
    st_col  = "#2ecc71" if st == "UP" else "#e74c3c"
    rsi_col = (
        "#c0392b" if rsi >= 70 else
        "#2ecc71" if rsi <= 30 else
        "#e67e22" if rsi >= 60 else
        "#52be80" if rsi <= 45 else "#bdc3c7"
    )
    hh_col = "#2ecc71" if ("HH" in hh_ll and "HL" in hh_ll) else (
             "#e74c3c" if ("LH" in hh_ll and "LL" in hh_ll) else "#7f8c8d")
    return (
        f'<div class="tech-block">'
        f'<div class="tech-title">TECHNICALS <span class="tech-sub">15-min</span></div>'
        f'<div class="tech-row"><span class="tl">Supertrend</span>'
        f'<span class="tv" style="color:{st_col};font-weight:700">{st} @ {td.get("supertrend_level",0):,.0f}</span></div>'
        f'<div class="tech-row"><span class="tl">EMA20</span>'
        f'<span class="tv">{ema20:,.1f} <small style="color:#94a3b8">({ema_rel})</small></span></div>'
        f'<div class="tech-row"><span class="tl">RSI14</span>'
        f'<span class="tv" style="color:{rsi_col};font-weight:600">{rsi} <small>[{td.get("rsi_zone","—")}]</small></span></div>'
        f'<div class="tech-row"><span class="tl">HH/LL</span>'
        f'<span class="tv" style="color:{hh_col}">{hh_ll}</span></div>'
        f'<div class="tech-row"><span class="tl">RSI Div</span>'
        f'<span class="tv">{div}</span></div>'
        f'</div>'
    )


def get_technicals_css():
    return """
.tech-block{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);
  border-radius:8px;padding:10px 14px;margin:8px 0}
.tech-title{font-size:10px;font-weight:700;letter-spacing:.08em;color:#94a3b8;
  text-transform:uppercase;margin-bottom:8px}
.tech-sub{font-size:9px;font-weight:400;color:#64748b;margin-left:6px}
.tech-row{display:flex;justify-content:space-between;align-items:center;
  padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.04)}
.tech-row:last-child{border-bottom:none}
.tl{font-size:11px;color:#94a3b8}.tv{font-size:11px;color:#e2e8f0}
"""
