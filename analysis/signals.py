"""
analysis/signals.py — Signal generation (directional bias from PCR + Max Pain).
"""

from config.settings import (
    PCR_STRONG_BULL, PCR_MILD_BULL, PCR_MILD_BEAR, PCR_STRONG_BEAR,
    MAX_PAIN_GAP_PCT, ALERT_PCR_CROSS, ALERT_PAIN_GAP,
)
from core.state import BotState


def generate_signal(state: BotState, symbol: str, pcr: float,
                    spot: float, max_pain: float) -> tuple[str, list]:
    """
    Generate directional signal from PCR and Max Pain gap.
    Returns (direction_string, list_of_reasons).
    """
    reasons = []
    scores = []

    # Rule 1 — PCR level
    if pcr >= PCR_STRONG_BULL:
        scores.append(+2)
        reasons.append(f"PCR {pcr} ≥ {PCR_STRONG_BULL} → Heavy PUT writing → Bullish")
    elif pcr >= PCR_MILD_BULL:
        scores.append(+1)
        reasons.append(f"PCR {pcr} in mild bullish zone ({PCR_MILD_BULL}–{PCR_STRONG_BULL})")
    elif pcr <= PCR_STRONG_BEAR:
        scores.append(-2)
        reasons.append(f"PCR {pcr} ≤ {PCR_STRONG_BEAR} → Heavy CALL writing → Bearish")
    elif pcr <= PCR_MILD_BEAR:
        scores.append(-1)
        reasons.append(f"PCR {pcr} in mild bearish zone ({PCR_STRONG_BEAR}–{PCR_MILD_BEAR})")
    else:
        scores.append(0)
        reasons.append(f"PCR {pcr} in neutral zone ({PCR_MILD_BEAR}–{PCR_MILD_BULL})")

    # Rule 2 — Spot vs Max Pain
    if max_pain > 0:
        gap = (spot - max_pain) / max_pain * 100
        if gap > MAX_PAIN_GAP_PCT:
            scores.append(-1)
            reasons.append(f"Spot {spot:,.0f} is {gap:.1f}% ABOVE Max Pain {max_pain:,.0f} → pullback likely")
        elif gap < -MAX_PAIN_GAP_PCT:
            scores.append(+1)
            reasons.append(f"Spot {spot:,.0f} is {abs(gap):.1f}% BELOW Max Pain {max_pain:,.0f} → bounce likely")
        else:
            reasons.append(f"Spot near Max Pain {max_pain:,.0f} (gap: {gap:+.1f}%)")

    # Rule 3 — PCR crossover alert
    prev = state.prev_pcr.get(symbol, pcr)
    if prev < ALERT_PCR_CROSS <= pcr and max_pain > 0:
        gap_abs = abs((spot - max_pain) / max_pain * 100)
        if gap_abs >= ALERT_PAIN_GAP:
            reasons.insert(0,
                f"🚨 ALERT: PCR just crossed {ALERT_PCR_CROSS} AND Spot/MaxPain gap = {gap_abs:.1f}%"
            )
    state.prev_pcr[symbol] = pcr

    total = sum(scores)
    if total >= 2:    direction = "🟢🟢 STRONG BULLISH"
    elif total == 1:  direction = "🟢 MILD BULLISH"
    elif total <= -2: direction = "🔴🔴 STRONG BEARISH"
    elif total == -1: direction = "🔴 MILD BEARISH"
    else:             direction = "⚪ NEUTRAL"

    return direction, reasons
