"""
analysis/futures.py — Futures data fetch + 3-min OHLCV candle persistence.

CHANGES (Phase 1 Rank 1 — OBJ 2):
  - fetch_futures()            — unchanged core logic
  - fetch_futures_candles()    — NEW: fetches 3-min OHLCV candles for futures
                                  and stores them in the FUTURES_CANDLES sheet
"""

import datetime
import pandas as pd

from config.settings import SPOT_QUOTE_KEYS, IST, INDEX_TOKENS
from core.state import BotState
from core.kite_client import get_nfo_instruments, fetch_quotes, fetch_spot_price
from utils.logger import log


def fetch_futures(state: BotState, symbol: str) -> dict:
    """
    Fetch current-month futures LTP, basis, and pivot levels.
    Auto-switches to next-month if ≤7 days to expiry.
    """
    if not state.kite:
        return {}
    try:
        instruments = get_nfo_instruments(state)
        if instruments.empty:
            return {}

        mask = (instruments["name"] == symbol) & (instruments["instrument_type"] == "FUT")
        df = instruments[mask].copy()
        df["expiry"] = pd.to_datetime(df["expiry"]).dt.date

        today           = datetime.date.today()
        future_expiries = sorted(e for e in df["expiry"].unique() if e >= today)
        if not future_expiries:
            return {}

        nearest        = future_expiries[0]
        days_to_expiry = (nearest - today).days
        if days_to_expiry <= 7 and len(future_expiries) > 1:
            chosen, contract = future_expiries[1], "Next Month"
        else:
            chosen, contract = nearest, "Current Month"

        row           = df[df["expiry"] == chosen].iloc[0]
        tradingsymbol = row["tradingsymbol"]
        fut_token     = int(row["instrument_token"])

        q   = fetch_quotes(state, [f"NFO:{tradingsymbol}"])
        ltp = q[f"NFO:{tradingsymbol}"]["last_price"] if q else 0

        spot    = fetch_spot_price(state, symbol)
        basis   = round(ltp - spot, 2)
        basis_pct = round(basis / spot * 100, 3) if spot else 0

        # Update spot cache
        state.last_spot[symbol] = spot

        return {
            "symbol":    symbol,
            "contract":  contract,
            "expiry":    str(chosen),
            "days_left": days_to_expiry,
            "ltp":       ltp,
            "spot":      spot,
            "basis":     basis,
            "basis_pct": basis_pct,
            "token":     fut_token,
            "tradingsymbol": tradingsymbol,
        }
    except Exception as e:
        log.error(f"Futures {symbol} error: {e}")
        return {}


def fetch_futures_candles(state: BotState, symbol: str, fut_data: dict) -> list:
    """
    Fetch 3-min OHLCV candles for the active futures contract.
    Returns list of candle dicts: {date, open, high, low, close, volume}

    Called every scan and passed to excel_writer for FUTURES_CANDLES persistence.
    fut_data must be the result of fetch_futures() (provides token + expiry).
    """
    if not state.kite or not fut_data:
        return []

    token = fut_data.get("token", 0)
    if not token:
        # Fallback: try to get token from instruments
        try:
            instruments = get_nfo_instruments(state)
            mask = (
                (instruments["name"] == symbol)
                & (instruments["instrument_type"] == "FUT")
                & (instruments["expiry"] == pd.to_datetime(fut_data.get("expiry", "")).date()
                   if fut_data.get("expiry") else True)
            )
            df = instruments[mask]
            if not df.empty:
                token = int(df.iloc[0]["instrument_token"])
        except Exception:
            pass

    if not token:
        return []

    try:
        now_ist     = datetime.datetime.now(IST)
        today       = now_ist.date()
        market_open = datetime.datetime.combine(today, datetime.time(9, 0))
        fetch_to    = now_ist.replace(tzinfo=None)

        candles = state.kite.historical_data(
            instrument_token=token,
            from_date=market_open,
            to_date=fetch_to,
            interval="3minute",
        )
        log.debug(f"[Futures] {symbol} candles fetched: {len(candles) if candles else 0}")
        return candles or []
    except Exception as e:
        log.warning(f"[Futures] {symbol} candle fetch error: {e}")
        return []
