"""
indicators/greeks_per_strike.py — Per-strike Greeks computation (Delta, Theta, Gamma, Vega).

PHASE 1 RANK 1 (OBJ 8.ii):
  Extends the Black-Scholes engine already in iv_tracker.py to compute all four
  Greeks for every strike in the ATM window.  Results are:
    1. Stored in Excel (OI sheets) via excel_writer.save_oi_with_greeks()
    2. Available to the dashboard for display alongside OI data

Usage:
    from indicators.greeks_per_strike import compute_greeks_for_chain
    greeks = compute_greeks_for_chain(chain, spot, expiry_date, avg_iv)
    # greeks = {strike: {"CE": {delta, theta, gamma, vega}, "PE": {...}}}
"""

import datetime
import math

RISK_FREE_RATE = 0.065   # match iv_tracker.py


# ─────────────────────────────────────────────────────────────────────────────
#  BLACK-SCHOLES PRIMITIVES (duplicated for module independence)
# ─────────────────────────────────────────────────────────────────────────────

def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

def _d1d2(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0, 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2

def bs_delta(S, K, T, r, sigma, opt):
    d1, _ = _d1d2(S, K, T, r, sigma)
    if T <= 0 or sigma <= 0:
        return (1.0 if S > K else 0.0) if opt == "CE" else (-1.0 if S < K else 0.0)
    return round(_norm_cdf(d1) if opt == "CE" else _norm_cdf(d1) - 1.0, 4)

def bs_theta(S, K, T, r, sigma, opt):
    """Daily theta in index points."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1, d2 = _d1d2(S, K, T, r, sigma)
    common  = -(S * _norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
    if opt == "CE":
        theta_ann = common - r * K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        theta_ann = common + r * K * math.exp(-r * T) * _norm_cdf(-d2)
    return round(theta_ann / 365.0, 4)

def bs_gamma(S, K, T, r, sigma):
    """Gamma (same for CE and PE)."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1, _ = _d1d2(S, K, T, r, sigma)
    return round(_norm_pdf(d1) / (S * sigma * math.sqrt(T)), 6)

def bs_vega(S, K, T, r, sigma):
    """Vega per 1% IV move (divide annual vega by 100)."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1, _ = _d1d2(S, K, T, r, sigma)
    return round(S * _norm_pdf(d1) * math.sqrt(T) / 100.0, 4)

def _dte_years(expiry_date) -> float:
    today = datetime.date.today()
    if isinstance(expiry_date, str):
        try:
            expiry_date = datetime.date.fromisoformat(expiry_date)
        except ValueError:
            return 0.0
    dte = (expiry_date - today).days
    return max(dte, 1) / 365.0


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def compute_greeks_for_chain(
    chain: dict,
    spot: float,
    expiry_date,
    avg_iv: float = 0.2,
    strikes_window: list = None,
) -> dict:
    """
    Compute Delta, Theta, Gamma, Vega for every strike in the chain
    (or just those in strikes_window if provided).

    Args:
        chain:          {strike: {"CE": {...}, "PE": {...}}}
        spot:           Current index spot price
        expiry_date:    str "YYYY-MM-DD" or datetime.date
        avg_iv:         ATM average IV (decimal, e.g. 0.13 for 13%).
                        Used as the base sigma for OTM/ITM strikes where
                        individual IV solving would be unreliable.
        strikes_window: List of strikes to compute. Defaults to all in chain.

    Returns:
        {
          strike: {
            "CE": {"delta": 0.52, "theta": -12.3, "gamma": 0.0004, "vega": 0.82},
            "PE": {"delta": -0.48, "theta": -11.8, "gamma": 0.0004, "vega": 0.82},
          },
          ...
        }
    """
    if not chain or spot <= 0:
        return {}

    T      = _dte_years(expiry_date)
    r      = RISK_FREE_RATE
    sigma  = avg_iv if avg_iv > 0.01 else 0.15   # floor at 1% to avoid math errors
    target = strikes_window if strikes_window is not None else sorted(chain.keys())

    result = {}
    for strike in target:
        if strike not in chain:
            continue
        K = float(strike)
        result[K] = {
            "CE": {
                "delta": bs_delta(spot, K, T, r, sigma, "CE"),
                "theta": bs_theta(spot, K, T, r, sigma, "CE"),
                "gamma": bs_gamma(spot, K, T, r, sigma),
                "vega":  bs_vega(spot, K, T, r, sigma),
            },
            "PE": {
                "delta": bs_delta(spot, K, T, r, sigma, "PE"),
                "theta": bs_theta(spot, K, T, r, sigma, "PE"),
                "gamma": bs_gamma(spot, K, T, r, sigma),
                "vega":  bs_vega(spot, K, T, r, sigma),
            },
        }
    return result
