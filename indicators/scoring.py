"""
indicators/scoring.py — Unified scoring interface.

Provides a single function that collects scores from all indicator phases.
"""

from indicators.vwap import score_vwap
from indicators.technicals import score_technicals
from indicators.iv_tracker import score_iv
from indicators.oi_concentration import score_oi_concentration


def get_all_scoring_functions() -> dict:
    """Return all scoring functions for injection into trade_setup.score_trade_setups()."""
    return {
        "score_vwap_fn": score_vwap,
        "score_technicals_fn": score_technicals,
        "score_iv_fn": score_iv,
        "score_oi_concentration_fn": score_oi_concentration,
    }
