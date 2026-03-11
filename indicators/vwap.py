"""
indicators/vwap.py — Phase 1: VWAP Engine.

Contains all VWAP computation, scoring, formatting, and HTML building.
Extracted from the original monolithic indicators.py.

NOTE: The full implementation of compute_vwap(), score_vwap(), etc. should be
copied from the original indicators.py (lines 78-726). The function signatures
and return types are identical — only the imports change.

The key import change: instead of hardcoded INDEX_TOKENS, import from config:
    from config.settings import INDEX_TOKENS, SPOT_QUOTE_KEYS, IST
    from core.kite_client import get_futures_token  # instead of local _get_futures_token
"""

# ── Re-export stub ───────────────────────────────────────────────────────────
# TODO: Copy full implementation from original indicators.py lines 78-726
# Update imports from config.settings and core.kite_client

import datetime
import math
from config.settings import IST, INDEX_TOKENS, SPOT_QUOTE_KEYS
from utils.logger import log


def _get_futures_token_compat(kite, symbol):
    """Compatibility wrapper — delegates to core.kite_client."""
    from core.state import BotState
    # Create a temporary state for backwards compatibility
    state = BotState()
    state.kite = kite
    from core.kite_client import get_futures_token
    return get_futures_token(state, symbol)


# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 1 — VWAP ENGINE (Full implementation)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_vwap(kite, symbol: str) -> dict:
    """Calculate intraday VWAP with bands, AVWAP, and slope."""
    if kite is None:
        return {}

    token = INDEX_TOKENS.get(symbol)
    if not token:
        return {"error": f"Unknown symbol: {symbol}"}

    try:
        now_ist = datetime.datetime.now(IST)
        today = now_ist.date()
        market_open = datetime.datetime.combine(today, datetime.time(9, 0))
        fetch_to = now_ist.replace(tzinfo=None)

        candles = kite.historical_data(
            instrument_token=token, from_date=market_open,
            to_date=fetch_to, interval="3minute",
        )
        if not candles or len(candles) < 2:
            return {"error": "Not enough candle data"}

        # Patch with futures volume
        fut_token = _get_futures_token_compat(kite, symbol)
        if fut_token:
            try:
                fut_candles = kite.historical_data(
                    instrument_token=fut_token, from_date=market_open,
                    to_date=fetch_to, interval="3minute",
                )
                vol_map = {c["date"]: c["volume"] for c in fut_candles} if fut_candles else {}
                for c in candles:
                    c["volume"] = vol_map.get(c["date"], 0)
            except Exception:
                pass

        cum_tpv = cum_vol = cum_tpv2 = 0.0
        vwap_series = []

        for c in candles:
            vol = c["volume"]
            if vol <= 0:
                vwap_series.append(vwap_series[-1] if vwap_series else 0)
                continue
            tp = (c["high"] + c["low"] + c["close"]) / 3.0
            cum_tpv += tp * vol
            cum_vol += vol
            cum_tpv2 += (tp ** 2) * vol
            vwap_series.append(cum_tpv / cum_vol)

        if cum_vol == 0:
            return {"error": "All candles have zero volume"}

        vwap = cum_tpv / cum_vol
        variance = max(0.0, (cum_tpv2 / cum_vol) - (vwap ** 2))
        sigma = math.sqrt(variance)

        # Slope
        valid_series = [v for v in vwap_series if v > 0]
        slope = 0.0
        slope_dir = "FLAT"
        if len(valid_series) >= 3:
            recent = valid_series[-3:]
            slope = round((recent[-1] - recent[0]) / 2.0, 2)
            slope_dir = "UP" if slope > 1.0 else ("DOWN" if slope < -1.0 else "FLAT")

        # Weekly AVWAP
        avwap_weekly = _compute_weekly_avwap(kite, symbol, token, today)

        # Spot
        spot = 0.0
        try:
            sq = kite.quote([SPOT_QUOTE_KEYS[symbol]])
            spot = sq[SPOT_QUOTE_KEYS[symbol]]["last_price"]
        except Exception:
            spot = candles[-1]["close"]

        tolerance = sigma * 0.05
        if spot > vwap + tolerance:
            position = "ABOVE"
        elif spot < vwap - tolerance:
            position = "BELOW"
        else:
            position = "AT"

        return {
            "vwap": round(vwap, 2), "band_1up": round(vwap + sigma, 2),
            "band_1dn": round(vwap - sigma, 2), "band_2up": round(vwap + 2*sigma, 2),
            "band_2dn": round(vwap - 2*sigma, 2), "sigma": round(sigma, 2),
            "avwap_weekly": avwap_weekly, "slope": slope, "slope_direction": slope_dir,
            "position": position, "spot": spot, "candles_used": len(candles),
            "as_of": str(candles[-1]["date"]), "error": None,
        }
    except Exception as e:
        return {"error": str(e)}


def _compute_weekly_avwap(kite, symbol, token, today):
    """Anchored VWAP from Monday's open."""
    try:
        days_since_monday = today.weekday()
        monday = today - datetime.timedelta(days=days_since_monday)
        now_ist = datetime.datetime.now(IST)
        fetch_from = datetime.datetime.combine(monday, datetime.time(9, 0))
        fetch_to = now_ist.replace(tzinfo=None)

        candles = kite.historical_data(instrument_token=token, from_date=fetch_from,
                                        to_date=fetch_to, interval="3minute")
        if not candles:
            return 0.0

        fut_token = _get_futures_token_compat(kite, symbol)
        if fut_token:
            try:
                fc = kite.historical_data(instrument_token=fut_token, from_date=fetch_from,
                                          to_date=fetch_to, interval="3minute")
                vm = {c["date"]: c["volume"] for c in fc} if fc else {}
                for c in candles:
                    c["volume"] = vm.get(c["date"], 0)
            except Exception:
                pass

        cum_tpv = cum_vol = 0.0
        for c in candles:
            if c["volume"] <= 0:
                continue
            tp = (c["high"] + c["low"] + c["close"]) / 3.0
            cum_tpv += tp * c["volume"]
            cum_vol += c["volume"]
        return round(cum_tpv / cum_vol, 2) if cum_vol > 0 else 0.0
    except Exception:
        return 0.0


def compute_all_vwap(kite, symbols=None) -> dict:
    if symbols is None:
        symbols = ["NIFTY", "BANKNIFTY"]
    result = {}
    for sym in symbols:
        result[sym] = compute_vwap(kite, sym)
        vd = result[sym]
        if vd and not vd.get("error"):
            log.info(f"[VWAP] {sym} VWAP:{vd['vwap']:,.2f} Slope:{vd['slope_direction']} Spot:{vd['position']}")
        else:
            log.warning(f"[VWAP] {sym} {vd.get('error', 'unavailable') if vd else 'kite unavailable'}")
    return result


def score_vwap(vwap_data: dict) -> dict:
    """Translate VWAP data into setup score contributions."""
    scores = {"long_ce": 0, "long_pe": 0, "short_straddle": 0, "short_strangle": 0}
    notes = []
    if not vwap_data or vwap_data.get("error"):
        return {**scores, "notes": ["VWAP data unavailable"]}

    position = vwap_data.get("position", "")
    slope = vwap_data.get("slope_direction", "")
    spot = vwap_data.get("spot", 0)
    vwap = vwap_data.get("vwap", 0)
    b1up = vwap_data.get("band_1up", 0)
    b1dn = vwap_data.get("band_1dn", 0)
    b2up = vwap_data.get("band_2up", 0)
    b2dn = vwap_data.get("band_2dn", 0)
    avwap_w = vwap_data.get("avwap_weekly", 0)

    if vwap == 0 or spot == 0:
        return {**scores, "notes": ["VWAP or spot is zero"]}

    if position == "ABOVE":
        scores["long_ce"] += 2; scores["short_strangle"] += 1
        notes.append(f"Spot ABOVE VWAP {vwap:,.2f} → bullish")
    elif position == "BELOW":
        scores["long_pe"] += 2; scores["short_strangle"] += 1
        notes.append(f"Spot BELOW VWAP {vwap:,.2f} → bearish")
    else:
        scores["short_straddle"] += 1; scores["short_strangle"] += 1

    if slope == "UP":
        scores["long_ce"] += 1
    elif slope == "DOWN":
        scores["long_pe"] += 1
    else:
        scores["short_straddle"] += 1

    if b2up > 0 and spot >= b2up:
        scores["long_pe"] += 2; scores["short_straddle"] += 1
    elif b2dn > 0 and spot <= b2dn:
        scores["long_ce"] += 2; scores["short_straddle"] += 1
    else:
        scores["short_straddle"] += 1

    if avwap_w > 0:
        avwap_diff_pct = abs(spot - avwap_w) / avwap_w * 100
        if avwap_diff_pct < 0.3:
            if position == "ABOVE" and slope == "UP":
                scores["long_ce"] += 1
            elif position == "BELOW" and slope == "DOWN":
                scores["long_pe"] += 1

    return {**scores, "notes": notes}


# ── Excel / Telegram / HTML stubs ─────────────────────────────────────────────
def get_vwap_excel_headers(): return ["VWAP","VWAP_Band1Up","VWAP_Band1Dn","VWAP_Band2Up","VWAP_Band2Dn","VWAP_Weekly_AVWAP","VWAP_Slope","VWAP_Position"]
def get_vwap_excel_values(vd):
    if not vd or vd.get("error"): return [0,0,0,0,0,0,"—","—"]
    return [vd.get("vwap",0),vd.get("band_1up",0),vd.get("band_1dn",0),vd.get("band_2up",0),vd.get("band_2dn",0),vd.get("avwap_weekly",0),f"{vd.get('slope',0):+.2f}",vd.get("position","—")]

def format_vwap_telegram_line(vd, symbol):
    if not vd or vd.get("error"): return "VWAP: unavailable"
    vwap=vd.get("vwap",0); pos=vd.get("position","AT"); pct=round((vd.get("spot",0)-vwap)/vwap*100,2) if vwap else 0
    emoji="🟢" if pos=="ABOVE" else ("🔴" if pos=="BELOW" else "⚪")
    return f"{emoji} VWAP: <b>{vwap:,.2f}</b> Spot {pos} ({pct:+.2f}%)"

def format_vwap_premarket_line(vd):
    if not vd or vd.get("error"): return "  VWAP: awaiting market open data"
    lines=[]
    if vd.get("avwap_weekly",0)>0: lines.append(f"  Weekly AVWAP: <b>{vd['avwap_weekly']:,.2f}</b>")
    if vd.get("vwap",0)>0: lines.append(f"  Daily VWAP ref: <b>{vd['vwap']:,.2f}</b>")
    return "\n".join(lines) if lines else "  VWAP: awaiting first scan"

def build_vwap_html(vd, symbol): return ""  # TODO: Copy from original indicators.py lines 504-591
def get_vwap_css(): return ""  # TODO: Copy from original indicators.py lines 594-672
