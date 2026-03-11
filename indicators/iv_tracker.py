"""
indicators/iv_tracker.py — IV + Straddle Premium Tracker with Black-Scholes Greeks.

Phase 1 Rank 1:
  - compute_iv()  fetches ATM CE + PE prices, solves IV via Newton-Raphson
  - Greeks:       Delta (CE & PE), Theta (CE & PE) — daily time-decay in index points
  - Straddle premium + straddle % of spot
  - IV skew (PE IV - CE IV)
  - IV rank proxy from straddle % (LOW / MEDIUM / HIGH)
"""

import datetime
import math

from config.settings import IST
from utils.logger import log

# RBI repo rate approximation — update quarterly if needed
RISK_FREE_RATE = 0.065


# ═══════════════════════════════════════════════════════════════════════════════
#  BLACK-SCHOLES ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs_price(S, K, T, r, sigma, opt):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0) if opt == "CE" else max(K - S, 0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if opt == "CE":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def _bs_delta(S, K, T, r, sigma, opt):
    if T <= 0 or sigma <= 0:
        return (1.0 if S > K else 0.0) if opt == "CE" else (-1.0 if S < K else 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return _norm_cdf(d1) if opt == "CE" else _norm_cdf(d1) - 1.0


def _bs_theta(S, K, T, r, sigma, opt):
    """Daily theta in index points (typically negative = time-decay)."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1    = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2    = d1 - sigma * math.sqrt(T)
    common = -(S * _norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
    if opt == "CE":
        theta_annual = common - r * K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        theta_annual = common + r * K * math.exp(-r * T) * _norm_cdf(-d2)
    return round(theta_annual / 365.0, 4)


def _compute_iv_newton(market_price, S, K, T, r, opt, tol=1e-5, max_iter=100):
    """Newton-Raphson IV solver. Returns sigma (decimal) or 0.0 on failure."""
    if T <= 0 or market_price <= 0:
        return 0.0
    intrinsic = max(S - K, 0) if opt == "CE" else max(K - S, 0)
    if market_price <= intrinsic:
        return 0.0
    sigma = 0.3
    for _ in range(max_iter):
        price = _bs_price(S, K, T, r, sigma, opt)
        if sigma > 0:
            d1   = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
            vega = S * _norm_pdf(d1) * math.sqrt(T)
        else:
            vega = 0
        if vega < 1e-10:
            break
        diff  = price - market_price
        if abs(diff) < tol:
            break
        sigma -= diff / vega
        sigma  = max(sigma, 1e-6)
    return round(sigma, 6) if 0.001 < sigma < 10 else 0.0


def _dte_years(expiry_date) -> float:
    today = datetime.date.today()
    if isinstance(expiry_date, str):
        try:
            expiry_date = datetime.date.fromisoformat(expiry_date)
        except ValueError:
            return 0.0
    dte = (expiry_date - today).days
    return max(dte, 1) / 365.0


# ═══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def compute_iv(kite, symbol: str, chain: dict, spot: float, expiry_date) -> dict:
    """
    Compute IV + Delta + Theta for ATM strike from live option chain.
    Returns dict with all IV/greeks fields, or {"error": ...} on failure.
    """
    if not chain or spot == 0:
        return {"error": "No chain or spot data"}

    T       = _dte_years(expiry_date)
    strikes = sorted(chain.keys())
    if not strikes:
        return {"error": "Empty chain"}

    atm     = min(strikes, key=lambda x: abs(x - spot))
    ce_data = chain.get(atm, {}).get("CE", {})
    pe_data = chain.get(atm, {}).get("PE", {})
    ce_ltp  = ce_data.get("lastPrice", 0.0)
    pe_ltp  = pe_data.get("lastPrice", 0.0)

    if ce_ltp <= 0 and pe_ltp <= 0:
        return {"error": "ATM CE and PE LTP both zero"}

    ce_iv  = _compute_iv_newton(ce_ltp, spot, atm, T, RISK_FREE_RATE, "CE") if ce_ltp > 0 else 0.0
    pe_iv  = _compute_iv_newton(pe_ltp, spot, atm, T, RISK_FREE_RATE, "PE") if pe_ltp > 0 else 0.0
    avg_iv = ((ce_iv + pe_iv) / 2.0) if (ce_iv > 0 and pe_iv > 0) else max(ce_iv, pe_iv)

    sigma    = avg_iv if avg_iv > 0 else 0.2
    ce_delta = round(_bs_delta(spot, atm, T, RISK_FREE_RATE, sigma, "CE"), 4)
    pe_delta = round(_bs_delta(spot, atm, T, RISK_FREE_RATE, sigma, "PE"), 4)
    ce_theta = _bs_theta(spot, atm, T, RISK_FREE_RATE, sigma, "CE")
    pe_theta = _bs_theta(spot, atm, T, RISK_FREE_RATE, sigma, "PE")

    straddle_pts = round(ce_ltp + pe_ltp, 2)
    straddle_pct = round(straddle_pts / spot * 100, 3) if spot else 0

    skew = round(pe_iv - ce_iv, 4)
    if skew > 0.02:    skew_label = "PUT SKEW — Downside fear"
    elif skew < -0.02: skew_label = "CALL SKEW — Upside demand"
    else:              skew_label = "BALANCED"

    if straddle_pct >= 4.0:   iv_rank = "HIGH"
    elif straddle_pct >= 2.5: iv_rank = "MEDIUM"
    else:                      iv_rank = "LOW"

    dte_days = max(0, (datetime.date.fromisoformat(str(expiry_date)) - datetime.date.today()).days
                   if expiry_date else 0)

    return {
        "atm_strike":    atm,
        "atm_ce_iv":     round(ce_iv * 100, 2),
        "atm_pe_iv":     round(pe_iv * 100, 2),
        "atm_iv_avg":    round(avg_iv * 100, 2),
        "atm_ce_delta":  ce_delta,
        "atm_pe_delta":  pe_delta,
        "atm_ce_theta":  ce_theta,
        "atm_pe_theta":  pe_theta,
        "straddle_pts":  straddle_pts,
        "straddle_pct":  straddle_pct,
        "skew":          round(skew * 100, 2),
        "skew_label":    skew_label,
        "iv_rank":       iv_rank,
        "iv_percentile": "—",
        "dte":           dte_days,
        "expiry":        str(expiry_date),
        "error":         None,
    }


def compute_all_iv(kite, oi_data_map: dict) -> dict:
    result = {}
    for sym, data in oi_data_map.items():
        if not data:
            result[sym] = {"error": "No OI data"}
            continue
        iv = compute_iv(
            kite, sym,
            data.get("chain", {}),
            data.get("spot", 0),
            data.get("expiry", ""),
        )
        result[sym] = iv
        if iv and not iv.get("error"):
            log.info(
                f"[IV] {sym}  ATM:{iv['atm_strike']:,.0f}  "
                f"CE_IV:{iv['atm_ce_iv']:.1f}%  PE_IV:{iv['atm_pe_iv']:.1f}%  "
                f"Straddle:{iv['straddle_pts']:.0f}pts({iv['straddle_pct']:.2f}%)  "
                f"ΔCE:{iv['atm_ce_delta']:.3f}  ΘCE:{iv['atm_ce_theta']:.2f}"
            )
        else:
            log.warning(f"[IV] {sym}: {iv.get('error','unavailable') if iv else 'none'}")
    return result


def score_iv(iv_data: dict) -> dict:
    scores = {"long_ce": 0, "long_pe": 0, "short_straddle": 0, "short_strangle": 0}
    notes  = []
    if not iv_data or iv_data.get("error"):
        return {**scores, "notes": ["IV unavailable"]}

    rank      = iv_data.get("iv_rank", "MEDIUM")
    skew_lbl  = iv_data.get("skew_label", "BALANCED")
    strdl_pct = iv_data.get("straddle_pct", 0)

    if rank == "HIGH":
        scores["short_straddle"] += 2; scores["short_strangle"] += 2
        notes.append(f"IV HIGH (straddle {strdl_pct:.1f}%) → sell premium")
    elif rank == "LOW":
        scores["long_ce"] += 1; scores["long_pe"] += 1
        notes.append(f"IV LOW (straddle {strdl_pct:.1f}%) → buy options")

    if "PUT SKEW" in skew_lbl:
        scores["long_pe"] += 1; scores["short_strangle"] += 1
        notes.append("Put skew — downside hedging")
    elif "CALL SKEW" in skew_lbl:
        scores["long_ce"] += 1; scores["short_strangle"] += 1
        notes.append("Call skew — upside demand")

    return {**scores, "notes": notes}


# ── Excel helpers ─────────────────────────────────────────────────────────────

def get_iv_excel_headers():
    return [
        "Timestamp", "Symbol",
        "ATM_Strike",
        "ATM_CE_IV%", "ATM_PE_IV%", "ATM_IV_Avg%",
        "ATM_CE_Delta", "ATM_PE_Delta",
        "ATM_CE_Theta", "ATM_PE_Theta",
        "Straddle_Pts", "Straddle_Pct%",
        "Skew%", "Skew_Label",
        "IV_Rank", "DTE", "Expiry",
    ]


def get_iv_excel_values(iv_data, symbol, timestamp):
    if not iv_data or iv_data.get("error"):
        return [timestamp, symbol] + ["—"] * 15
    return [
        timestamp, symbol,
        iv_data.get("atm_strike", 0),
        iv_data.get("atm_ce_iv", 0),  iv_data.get("atm_pe_iv", 0),  iv_data.get("atm_iv_avg", 0),
        iv_data.get("atm_ce_delta", 0), iv_data.get("atm_pe_delta", 0),
        iv_data.get("atm_ce_theta", 0), iv_data.get("atm_pe_theta", 0),
        iv_data.get("straddle_pts", 0), iv_data.get("straddle_pct", 0),
        iv_data.get("skew", 0), iv_data.get("skew_label", "—"),
        iv_data.get("iv_rank", "—"), iv_data.get("dte", 0), iv_data.get("expiry", "—"),
    ]


def format_iv_telegram_line(iv_data, symbol):
    if not iv_data or iv_data.get("error"):
        return f"[{symbol}] IV: unavailable"
    return (
        f"📊 {symbol}  ATM:{iv_data.get('atm_strike',0):,.0f}  "
        f"CE_IV:{iv_data.get('atm_ce_iv',0):.1f}%  PE_IV:{iv_data.get('atm_pe_iv',0):.1f}%  "
        f"Straddle:{iv_data.get('straddle_pts',0):.0f}pts  "
        f"ΔCE:{iv_data.get('atm_ce_delta',0):.3f}  ΘCE:{iv_data.get('atm_ce_theta',0):.2f}  "
        f"[{iv_data.get('iv_rank','—')}]"
    )


def format_iv_premarket_line(iv_data, symbol):
    if not iv_data or iv_data.get("error"):
        return f"  {symbol} IV: awaiting first scan"
    return (
        f"  {symbol}: IV <b>{iv_data.get('atm_iv_avg',0):.1f}%</b>  "
        f"Straddle <b>{iv_data.get('straddle_pts',0):.0f}</b> pts  "
        f"[{iv_data.get('iv_rank','—')}]"
    )


def build_iv_html(iv_data, symbol):
    if not iv_data or iv_data.get("error"):
        return ""
    atm   = iv_data.get("atm_strike", 0)
    ce_iv = iv_data.get("atm_ce_iv", 0)
    pe_iv = iv_data.get("atm_pe_iv", 0)
    avg   = iv_data.get("atm_iv_avg", 0)
    c_dlt = iv_data.get("atm_ce_delta", 0)
    p_dlt = iv_data.get("atm_pe_delta", 0)
    c_tht = iv_data.get("atm_ce_theta", 0)
    p_tht = iv_data.get("atm_pe_theta", 0)
    strp  = iv_data.get("straddle_pts", 0)
    strpct = iv_data.get("straddle_pct", 0)
    skew  = iv_data.get("skew_label", "BALANCED")
    rank  = iv_data.get("iv_rank", "—")
    dte   = iv_data.get("dte", 0)
    rank_col = "#e74c3c" if rank == "HIGH" else "#2ecc71" if rank == "LOW" else "#e67e22"
    return (
        f'<div class="iv-block">'
        f'<div class="iv-title">IV &amp; GREEKS'
        f'<span class="iv-sub">BSM · ATM {int(atm):,} · DTE {dte}</span></div>'
        f'<div class="iv-grid">'
        f'<div class="iv-cell"><span class="ivl">CE IV</span><span class="ivv">{ce_iv:.1f}%</span></div>'
        f'<div class="iv-cell"><span class="ivl">PE IV</span><span class="ivv">{pe_iv:.1f}%</span></div>'
        f'<div class="iv-cell"><span class="ivl">Avg IV</span><span class="ivv">{avg:.1f}%</span></div>'
        f'<div class="iv-cell"><span class="ivl">IV Rank</span>'
        f'<span class="ivv" style="color:{rank_col};font-weight:700">{rank}</span></div>'
        f'</div>'
        f'<div class="iv-grid">'
        f'<div class="iv-cell"><span class="ivl">&Delta; CE</span><span class="ivv">{c_dlt:.3f}</span></div>'
        f'<div class="iv-cell"><span class="ivl">&Delta; PE</span><span class="ivv">{p_dlt:.3f}</span></div>'
        f'<div class="iv-cell"><span class="ivl">&Theta; CE/day</span><span class="ivv">{c_tht:.2f}</span></div>'
        f'<div class="iv-cell"><span class="ivl">&Theta; PE/day</span><span class="ivv">{p_tht:.2f}</span></div>'
        f'</div>'
        f'<div class="iv-row"><span class="ivl">Straddle</span>'
        f'<span class="ivv"><b>{strp:.1f}</b> pts &nbsp;({strpct:.2f}%)</span></div>'
        f'<div class="iv-row"><span class="ivl">Skew</span>'
        f'<span class="ivv">{skew}</span></div>'
        f'</div>'
    )


def get_iv_css():
    return """
.iv-block{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);
  border-radius:8px;padding:10px 14px;margin:8px 0}
.iv-title{font-size:10px;font-weight:700;letter-spacing:.08em;color:#94a3b8;
  text-transform:uppercase;margin-bottom:8px}
.iv-sub{font-size:9px;font-weight:400;color:#64748b;margin-left:6px}
.iv-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;margin-bottom:4px}
.iv-cell{background:rgba(255,255,255,0.03);border-radius:4px;padding:4px 6px;
  display:flex;flex-direction:column}
.ivl{font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.05em}
.ivv{font-size:11px;color:#e2e8f0;font-weight:500;margin-top:1px}
.iv-row{display:flex;justify-content:space-between;padding:3px 0;
  border-top:1px solid rgba(255,255,255,0.04)}
"""
