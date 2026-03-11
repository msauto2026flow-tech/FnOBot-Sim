"""
analysis/trade_setup.py — Multi-factor trade setup scoring engine.

Scores directional (BUY CE/PE) and neutral (SELL STRADDLE/STRANGLE) setups.
Integrates all phases: PCR, MaxPain, Futures, OI Delta, VWAP, Technicals, IV, OI Concentration.
"""

from config.settings import (
    PCR_STRONG_BULL, PCR_MILD_BULL, PCR_MILD_BEAR, PCR_STRONG_BEAR,
    MAX_PAIN_GAP_PCT,
)
from utils.logger import log


def score_trade_setups(
    symbol: str, analysis: dict, sr: dict, futures: dict, delta_data: dict,
    vwap_data: dict = None, tech_data: dict = None, iv_data: dict = None,
    conc_data: dict = None,
    # Scoring functions passed in to avoid circular imports
    score_vwap_fn=None, score_technicals_fn=None,
    score_iv_fn=None, score_oi_concentration_fn=None,
) -> dict:
    """
    Neutral scoring engine — scores both directional and short-premium setups.
    Score range: 0–10 for each setup type.

    Supertrend HARD OVERRIDE: counter-trend directional trades are capped at 3.
    """
    pcr = analysis.get("pcr", 0)
    spot = analysis.get("atm", 0)
    max_pain = analysis.get("max_pain", 0)
    basis = futures.get("basis", 0)
    mood = delta_data.get("mood", "")

    scores = {"long_ce": 0, "long_pe": 0, "short_straddle": 0, "short_strangle": 0}
    notes = []

    # PCR contribution
    if pcr >= PCR_STRONG_BULL:
        scores["long_ce"] += 3; scores["short_strangle"] += 1
        notes.append(f"PCR {pcr} strongly bullish")
    elif pcr >= PCR_MILD_BULL:
        scores["long_ce"] += 2; scores["short_strangle"] += 2
        notes.append(f"PCR {pcr} mildly bullish")
    elif pcr <= PCR_STRONG_BEAR:
        scores["long_pe"] += 3; scores["short_strangle"] += 1
        notes.append(f"PCR {pcr} strongly bearish")
    elif pcr <= PCR_MILD_BEAR:
        scores["long_pe"] += 2; scores["short_strangle"] += 2
        notes.append(f"PCR {pcr} mildly bearish")
    else:
        scores["short_straddle"] += 2; scores["short_strangle"] += 2
        notes.append(f"PCR {pcr} neutral — range likely")

    # Max Pain gap
    if max_pain > 0 and spot > 0:
        gap = (spot - max_pain) / max_pain * 100
        if gap > MAX_PAIN_GAP_PCT:
            scores["long_pe"] += 2; scores["short_straddle"] += 1
        elif gap < -MAX_PAIN_GAP_PCT:
            scores["long_ce"] += 2; scores["short_straddle"] += 1
        else:
            scores["short_straddle"] += 2; scores["short_strangle"] += 2

    # Futures basis
    if basis > 50:
        scores["long_ce"] += 1
    elif basis < -50:
        scores["long_pe"] += 1
    else:
        scores["short_straddle"] += 1

    # OI delta mood
    if "PE writing" in mood or "CE unwinding" in mood:
        scores["long_ce"] += 1; scores["short_strangle"] += 1
    elif "CE writing" in mood or "PE unwinding" in mood:
        scores["long_pe"] += 1; scores["short_strangle"] += 1
    elif "range" in mood.lower():
        scores["short_straddle"] += 1; scores["short_strangle"] += 1

    # Phase 1: VWAP
    tech_override = "NONE"
    if vwap_data and score_vwap_fn:
        vs = score_vwap_fn(vwap_data)
        for k in scores: scores[k] += vs.get(k, 0)
        notes += vs.get("notes", [])

    # Phase 2: Technicals (with Supertrend override)
    if tech_data and score_technicals_fn:
        ts = score_technicals_fn(tech_data)
        for k in scores: scores[k] += ts.get(k, 0)
        notes += ts.get("notes", [])
        tech_override = ts.get("supertrend_override", "NONE")
        if tech_override == "BEARISH_FILTER" and scores["long_ce"] > 3:
            scores["long_ce"] = 3
            notes.append("🔴 Supertrend HARD OVERRIDE: BUY CALL capped")
        elif tech_override == "BULLISH_FILTER" and scores["long_pe"] > 3:
            scores["long_pe"] = 3
            notes.append("🟢 Supertrend HARD OVERRIDE: BUY PUT capped")

    # Phase 3: IV
    if iv_data and score_iv_fn:
        ivs = score_iv_fn(iv_data)
        for k in scores: scores[k] += ivs.get(k, 0)
        notes += ivs.get("notes", [])

    # Phase 4: OI Concentration
    if conc_data and score_oi_concentration_fn:
        cs = score_oi_concentration_fn(conc_data)
        for k in scores: scores[k] += cs.get(k, 0)
        notes += cs.get("notes", [])

    # Cap at 10
    scores = {k: min(v, 10) for k, v in scores.items()}

    best = max(scores, key=scores.get)
    best_labels = {
        "long_ce": "📈 BUY CALL (Directional Bullish)",
        "long_pe": "📉 BUY PUT (Directional Bearish)",
        "short_straddle": "↔️ SHORT STRADDLE (Sell ATM CE+PE)",
        "short_strangle": "↔️ SHORT STRANGLE (Sell OTM CE+PE)",
    }

    return {
        "scores": scores, "best": best, "best_label": best_labels[best],
        "best_score": scores[best], "notes": notes, "tech_override": tech_override,
    }
