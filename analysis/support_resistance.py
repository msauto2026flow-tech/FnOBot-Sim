"""
analysis/support_resistance.py — Support & Resistance level computation.
"""

import datetime
from config.settings import IST, SPOT_QUOTE_KEYS
from core.state import BotState
from core.kite_client import fetch_spot_price
from config.holidays import prev_trading_day
from utils.logger import log


def compute_sr_levels(state: BotState, symbol: str, chain: dict,
                      spot: float, analysis: dict) -> dict:
    """
    Compute 3 support and 3 resistance levels from OI + previous day H/L.
    """
    strikes = sorted(chain.keys())
    if not strikes or not spot:
        return {}

    ce_oi_map = {s: chain[s].get("CE", {}).get("openInterest", 0) for s in strikes}
    pe_oi_map = {s: chain[s].get("PE", {}).get("openInterest", 0) for s in strikes}

    # Resistance: top CE OI strikes ABOVE spot
    res_strikes = sorted(
        [s for s in strikes if s > spot],
        key=lambda x: ce_oi_map[x], reverse=True
    )[:3]
    res_strikes = sorted(res_strikes)

    # Support: top PE OI strikes BELOW spot
    sup_strikes = sorted(
        [s for s in strikes if s < spot],
        key=lambda x: pe_oi_map[x], reverse=True
    )[:3]
    sup_strikes = sorted(sup_strikes, reverse=True)

    max_pain = analysis.get("max_pain", 0)
    atm = analysis.get("atm", 0)

    # Previous day OHLC
    prev_high, prev_low = _fetch_prev_day_hl(state, symbol)

    # Build annotated levels
    resistance = [
        {"level": s, "note": f"CE OI: {ce_oi_map[s]:,}" + (" + Max Pain" if s == max_pain else "")}
        for s in res_strikes
    ]
    support = [
        {"level": s, "note": f"PE OI: {pe_oi_map[s]:,}" + (" + Max Pain" if s == max_pain else "")}
        for s in sup_strikes
    ]

    # Add Max Pain if not in either list
    mp_in_res = any(r["level"] == max_pain for r in resistance)
    mp_in_sup = any(s["level"] == max_pain for s in support)
    if not mp_in_res and not mp_in_sup:
        entry = {"level": max_pain, "note": "Max Pain"}
        if max_pain > spot:
            resistance.insert(0, entry)
        else:
            support.insert(0, entry)

    return {
        "resistance": resistance[:3], "support": support[:3],
        "max_pain": max_pain, "prev_high": prev_high, "prev_low": prev_low,
        "atm": atm, "spot": spot,
    }


def _fetch_prev_day_hl(state: BotState, symbol: str) -> tuple:
    """Fetch previous trading day high/low."""
    try:
        spot_key = SPOT_QUOTE_KEYS.get(symbol, "")
        prev_day = prev_trading_day()
        ltp_data = state.kite.ltp([spot_key])
        spot_token = ltp_data[spot_key]["instrument_token"]
        hist = state.kite.historical_data(
            spot_token,
            datetime.datetime.combine(prev_day, datetime.time(9, 0)),
            datetime.datetime.combine(prev_day, datetime.time(15, 30)),
            "day",
        )
        if hist:
            return hist[-1]["high"], hist[-1]["low"]
    except Exception:
        pass
    return 0, 0
