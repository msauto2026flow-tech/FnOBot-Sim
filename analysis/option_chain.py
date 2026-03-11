"""
analysis/option_chain.py — Fetch & analyse option chains from Kite.

Provides: fetch_option_chain(), fetch_next_expiry_chain(), analyse_chain()

CHANGES (Phase 1 Rank 1):
  - fetch_option_chain()       — unchanged, fetches nearest expiry every scan
  - fetch_next_expiry_chain()  — NEW: fetches second expiry, called only every
                                  NEXT_EXPIRY_REFRESH_SCANS scans (≈15 min) to
                                  save API quota
  - analyse_chain()            — unchanged
"""

import datetime
import pandas as pd

from config.settings import (
    IST, STRIKES_AROUND_ATM, OI_SPIKE_PCT, SPOT_QUOTE_KEYS,
    NEXT_EXPIRY_REFRESH_SCANS,
)
from core.state import BotState
from core.kite_client import get_nfo_instruments, fetch_quotes
from utils.logger import log


# ─────────────────────────────────────────────────────────────────────────────
#  INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _build_chain_from_quotes(df, tokens, state, symbol) -> dict:
    """Fetch live quotes for given instrument tokens and build chain dict."""
    quotes = {}
    for i in range(0, len(tokens), 500):
        batch = tokens[i:i + 500]
        result = fetch_quotes(state, batch)
        if result:
            quotes.update(result)

    token_to_row = {str(row["instrument_token"]): row for _, row in df.iterrows()}

    chain = {}
    for token, q in quotes.items():
        row = token_to_row.get(token)
        if row is None:
            continue
        strike  = float(row["strike"])
        opttype = row["instrument_type"]
        oi = q.get("oi", 0) if q.get("oi", 0) > 0 else q.get("open_interest", 0)

        if strike not in chain:
            chain[strike] = {"CE": {}, "PE": {}}
        chain[strike][opttype] = {
            "openInterest":          oi,
            "changeinOpenInterest":  q.get("oi_day_change",
                                          q.get("oi_day_high", 0) - q.get("oi_day_low", 0)),
            "lastPrice":             q.get("last_price", 0),
            "volume":                q.get("volume", 0),
        }
    return chain


def _get_spot(state: BotState, symbol: str) -> float:
    """Fetch real-time spot price for symbol."""
    spot_key = SPOT_QUOTE_KEYS.get(symbol, "")
    try:
        sq = fetch_quotes(state, [spot_key])
        if sq and spot_key in sq:
            return sq[spot_key]["last_price"]
    except Exception as e:
        log.warning(f"Spot price error for {symbol}: {e}")
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC API — CURRENT EXPIRY (every scan)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_option_chain(state: BotState, symbol: str) -> dict | None:
    """
    Fetch complete option chain for the NEAREST expiry.
    Called every scan (every 3 min).

    Returns structured dict with spot, chain, expiry info, or None on failure.
    """
    if not state.kite:
        return None

    try:
        instruments = get_nfo_instruments(state)
        if instruments.empty:
            return None

        mask = (
            (instruments["name"] == symbol)
            & (instruments["instrument_type"].isin(["CE", "PE"]))
        )
        df = instruments[mask].copy()
        df["expiry"] = pd.to_datetime(df["expiry"]).dt.date

        today           = datetime.date.today()
        future_expiries = sorted(e for e in df["expiry"].unique() if e >= today)
        if not future_expiries:
            log.warning(f"No future expiries for {symbol}")
            return None

        chosen = future_expiries[0]
        df_exp = df[df["expiry"] == chosen]
        tokens = df_exp["instrument_token"].tolist()
        log.debug(f"{symbol} current expiry: {chosen}, strikes: {len(df_exp) // 2}")

        chain = _build_chain_from_quotes(df_exp, tokens, state, symbol)
        spot  = _get_spot(state, symbol)

        return {
            "symbol":   symbol,
            "expiry":   str(chosen),
            "expiries": [str(e) for e in future_expiries[:4]],
            "spot":     spot,
            "chain":    chain,
        }

    except Exception as e:
        log.error(f"Option chain error for {symbol}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC API — NEXT EXPIRY (every 15 min, controlled by scan_count)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_next_expiry_chain(state: BotState, symbol: str) -> dict | None:
    """
    Fetch option chain for the SECOND (next-week) expiry.

    Called only when scan_count % NEXT_EXPIRY_REFRESH_SCANS == 0,
    i.e. every ~15 min (5 scans × 3 min), to conserve API quota.

    Returns same structure as fetch_option_chain() but with next expiry date.
    Returns None if no second expiry exists (e.g., near monthly expiry).
    """
    if not state.kite:
        return None

    try:
        instruments = get_nfo_instruments(state)
        if instruments.empty:
            return None

        mask = (
            (instruments["name"] == symbol)
            & (instruments["instrument_type"].isin(["CE", "PE"]))
        )
        df = instruments[mask].copy()
        df["expiry"] = pd.to_datetime(df["expiry"]).dt.date

        today           = datetime.date.today()
        future_expiries = sorted(e for e in df["expiry"].unique() if e >= today)

        if len(future_expiries) < 2:
            log.debug(f"{symbol}: no next expiry available")
            return None

        chosen = future_expiries[1]   # <-- second expiry
        df_exp = df[df["expiry"] == chosen]
        tokens = df_exp["instrument_token"].tolist()
        log.debug(f"{symbol} next expiry: {chosen}, strikes: {len(df_exp) // 2}")

        chain = _build_chain_from_quotes(df_exp, tokens, state, symbol)
        spot  = state.last_spot.get(symbol, _get_spot(state, symbol))  # reuse cached spot

        return {
            "symbol":   symbol,
            "expiry":   str(chosen),
            "expiries": [str(e) for e in future_expiries[:4]],
            "spot":     spot,
            "chain":    chain,
            "is_next_expiry": True,
        }

    except Exception as e:
        log.error(f"Next-expiry chain error for {symbol}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC API — ANALYSIS (shared for both expiries)
# ─────────────────────────────────────────────────────────────────────────────

def analyse_chain(data: dict) -> dict:
    """
    Compute ATM, PCR, Max Pain, OI movers, OI spikes from chain data.
    Works identically for current-expiry and next-expiry chains.

    Returns dict with: atm, pcr, max_pain, window, movers, spikes,
                       total_ce, total_pe
    """
    chain  = data["chain"]
    spot   = data["spot"]
    strikes = sorted(chain.keys())

    if not strikes or spot == 0:
        return {}

    # ATM strike
    atm = min(strikes, key=lambda x: abs(x - spot))
    idx = strikes.index(atm)
    window = strikes[max(0, idx - STRIKES_AROUND_ATM): idx + STRIKES_AROUND_ATM + 1]

    # PCR
    total_ce = sum(chain[s].get("CE", {}).get("openInterest", 0) for s in strikes)
    total_pe = sum(chain[s].get("PE", {}).get("openInterest", 0) for s in strikes)
    pcr = round(total_pe / total_ce, 3) if total_ce else 0

    # Max Pain (O(n²) — acceptable for typical strike counts)
    pain = {}
    for target in strikes:
        loss = 0
        for s in strikes:
            ce_oi = chain[s].get("CE", {}).get("openInterest", 0)
            pe_oi = chain[s].get("PE", {}).get("openInterest", 0)
            loss += max(0, s - target) * ce_oi
            loss += max(0, target - s) * pe_oi
        pain[target] = loss
    max_pain = min(pain, key=pain.get)

    # Top 10 OI movers
    movers = []
    for s in strikes:
        for side in ["CE", "PE"]:
            ch = chain[s].get(side, {}).get("changeinOpenInterest", 0)
            oi = chain[s].get(side, {}).get("openInterest", 0)
            movers.append({"Strike": s, "Side": side, "OI": oi, "chOI": ch})
    movers_df = (
        pd.DataFrame(movers)
        .reindex(pd.DataFrame(movers)["chOI"].abs().sort_values(ascending=False).index)
        .head(10)
        .reset_index(drop=True)
    )

    # OI Spikes
    spikes = []
    for s in strikes:
        for side in ["CE", "PE"]:
            oi = chain[s].get(side, {}).get("openInterest", 0)
            ch = chain[s].get(side, {}).get("changeinOpenInterest", 0)
            if oi > 0:
                pct = ch / oi * 100
                if abs(pct) >= OI_SPIKE_PCT:
                    spikes.append({
                        "Strike": s, "Side": side, "OI": oi, "chOI": ch,
                        "Chg%": round(pct, 1),
                        "Type": "📈 WRITING" if ch > 0 else "📉 UNWINDING",
                    })
    spikes_df = (
        pd.DataFrame(spikes).sort_values("Chg%", key=abs, ascending=False).head(8).reset_index(drop=True)
        if spikes else pd.DataFrame()
    )

    return {
        "atm":      atm,
        "pcr":      pcr,
        "max_pain": max_pain,
        "window":   window,
        "movers":   movers_df,
        "spikes":   spikes_df,
        "total_ce": total_ce,
        "total_pe": total_pe,
    }
