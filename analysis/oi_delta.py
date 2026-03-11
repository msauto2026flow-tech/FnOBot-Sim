"""
analysis/oi_delta.py — 15-minute OI delta tracking and spike detection.

BUG FIX: Line 608 from v4 — PE_curr was incorrectly set to curr_ce.
         Now correctly uses curr_pe.
"""

import datetime

from config.settings import (
    IST, OI_DELTA_STRIKES, OI_DELTA_SPIKE_LOW, OI_DELTA_SPIKE_HIGH,
    OI_ALERT_COOLDOWN_EXTREME, OI_ALERT_COOLDOWN_SIGNIFICANT,
    OI_ALERT_MIN_ABS_OI,
)
from core.state import BotState
from utils.logger import log


def store_oi_snapshot(state: BotState, symbol: str, chain: dict):
    """Save current OI for all strikes. Updates 15-min and hourly snapshots."""
    snapshot = {}
    for strike, v in chain.items():
        snapshot[strike] = {
            "CE": v.get("CE", {}).get("openInterest", 0),
            "PE": v.get("PE", {}).get("openInterest", 0),
        }
    state.prev_oi_snapshot[symbol] = snapshot

    # Update hourly snapshot if 60+ minutes have passed
    now_ist = datetime.datetime.now(IST)
    last_hr = state.hour_snapshot_time.get(symbol)
    if last_hr is None or (now_ist - last_hr).seconds >= 3600:
        state.hour_oi_snapshot[symbol] = snapshot.copy()
        state.hour_snapshot_time[symbol] = now_ist


def store_prevday_oi(state: BotState, symbol: str, chain: dict):
    """Store EOD OI as previous day baseline."""
    snapshot = {}
    for strike, v in chain.items():
        snapshot[strike] = {
            "CE": v.get("CE", {}).get("openInterest", 0),
            "PE": v.get("PE", {}).get("openInterest", 0),
        }
    state.prevday_oi_snapshot[symbol] = snapshot


def compute_oi_delta(state: BotState, symbol: str, chain: dict, atm: float, strikes: list) -> dict:
    """
    Compare current OI vs previous 15-min snapshot.

    BUG FIX (v5): PE_curr now correctly uses curr_pe (was curr_ce in v4 line 608).

    Returns per-strike delta, summary stats, and spike alerts.
    """
    prev = state.prev_oi_snapshot.get(symbol, {})
    if not prev:
        return {}

    atm_idx = strikes.index(atm) if atm in strikes else len(strikes) // 2
    window = strikes[max(0, atm_idx - OI_DELTA_STRIKES): atm_idx + OI_DELTA_STRIKES + 1]

    deltas = []
    total_ce_add = 0
    total_pe_add = 0
    alerts = []

    # Decrement all cooldowns
    state.alert_cooldown = {k: max(0, v - 1) for k, v in state.alert_cooldown.items()}

    for s in window:
        prev_ce = prev.get(s, {}).get("CE", 0)
        prev_pe = prev.get(s, {}).get("PE", 0)
        curr_ce = chain.get(s, {}).get("CE", {}).get("openInterest", 0)
        curr_pe = chain.get(s, {}).get("PE", {}).get("openInterest", 0)

        d_ce = curr_ce - prev_ce
        d_pe = curr_pe - prev_pe
        total_ce_add += d_ce
        total_pe_add += d_pe

        ce_pct = round(d_ce / prev_ce * 100, 1) if prev_ce else 0
        pe_pct = round(d_pe / prev_pe * 100, 1) if prev_pe else 0

        # ═══ BUG FIX: PE_curr now correctly uses curr_pe (was curr_ce in v4) ═══
        deltas.append({
            "Strike": s,
            "CE_prev": prev_ce, "CE_curr": curr_ce, "CE_delta": d_ce, "CE_pct": ce_pct,
            "PE_prev": prev_pe, "PE_curr": curr_pe, "PE_delta": d_pe, "PE_pct": pe_pct,
        })

        # CE spike check
        _check_spike(state, alerts, symbol, s, "CE", prev_ce, curr_ce, d_ce, ce_pct)
        # PE spike check
        _check_spike(state, alerts, symbol, s, "PE", prev_pe, curr_pe, d_pe, pe_pct)

    mood = _determine_mood(total_ce_add, total_pe_add)

    return {
        "deltas": deltas, "alerts": alerts,
        "total_ce_add": total_ce_add, "total_pe_add": total_pe_add,
        "mood": mood,
    }


def _check_spike(state, alerts, symbol, strike, side, prev_oi, curr_oi, delta, pct):
    """Check for OI spike on a single strike/side and add alert if triggered."""
    ck = (symbol, int(strike), side)
    if (prev_oi >= OI_ALERT_MIN_ABS_OI
            and abs(pct) >= OI_DELTA_SPIKE_LOW
            and state.alert_cooldown.get(ck, 0) == 0):
        action = "WRITING ✍️" if delta > 0 else "UNWINDING 🚪"
        tier = "EXTREME" if abs(pct) >= OI_DELTA_SPIKE_HIGH else "SIGNIFICANT"
        cooldown = OI_ALERT_COOLDOWN_EXTREME if tier == "EXTREME" else OI_ALERT_COOLDOWN_SIGNIFICANT
        state.alert_cooldown[ck] = cooldown
        emoji = "🚨 EXTREME" if tier == "EXTREME" else "⚡ SPIKE"
        alerts.append((tier, {
            "symbol": symbol, "strike": int(strike), "side": side,
            "pct": pct, "delta": delta, "curr_oi": curr_oi,
            "action": action, "tier": tier,
            "msg": f"{emoji}: {symbol} {int(strike)} {side} {pct:+.1f}% ({action})",
        }))


def _determine_mood(ce_add: int, pe_add: int) -> str:
    """Determine market mood from net OI changes."""
    if ce_add > 0 and pe_add > 0:
        return "Both CE & PE being written — market range-bound"
    elif pe_add > ce_add and pe_add > 0:
        return "🟢 More PE writing than CE — Bullish bias"
    elif ce_add > pe_add and ce_add > 0:
        return "🔴 More CE writing than PE — Bearish bias"
    elif pe_add < 0 and ce_add < 0:
        return "⚪ Both CE & PE unwinding — participants exiting"
    elif pe_add < 0:
        return "🔴 PE unwinding — Bulls closing positions"
    elif ce_add < 0:
        return "🟢 CE unwinding — Bears closing positions"
    return "⚪ No significant OI change this cycle"
