"""
core/kite_client.py — Kite Connect wrapper with caching, retries, and login.

Key improvements over v4:
  - Instrument list cached once per day (was fetched 6-10x per scan)
  - Spot prices cached within a scan cycle
  - Retry with exponential backoff on API failures
  - Futures token lookup uses cached instruments
"""

import sys
import datetime
import pandas as pd
from typing import Optional

from config.settings import (
    KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN,
    KEYS_FILE, INDEX_TOKENS, SPOT_QUOTE_KEYS,
)
from core.state import BotState
from utils.logger import log
from utils.helpers import retry_on_failure

try:
    from kiteconnect import KiteConnect
    KITE_AVAILABLE = True
except ImportError:
    KITE_AVAILABLE = False
    log.critical("kiteconnect not installed. Run: pip install kiteconnect")
    sys.exit(1)


def init_kite(state: BotState) -> bool:
    """
    Initialise Kite Connect using saved access token.
    Returns True on success, False on failure.
    """
    if not KITE_API_KEY or not KITE_ACCESS_TOKEN:
        log.error("KITE_API_KEY or KITE_ACCESS_TOKEN missing")
        return False

    kite = KiteConnect(api_key=KITE_API_KEY)
    kite.set_access_token(KITE_ACCESS_TOKEN)

    try:
        kite.profile()
        state.kite = kite
        log.info("Kite Connect initialised and verified.")
        return True
    except Exception as e:
        log.error(f"Kite token invalid or expired: {e}")
        log.info("Run: python main.py --login  to get a new token.")
        return False


def generate_access_token():
    """Interactive login flow — run once each morning."""
    if not KITE_API_KEY or not KITE_API_SECRET:
        log.error("KITE_API_KEY or KITE_API_SECRET missing")
        return

    kite = KiteConnect(api_key=KITE_API_KEY)
    print("\n" + "=" * 60)
    print("  STEP 1 — Open this URL in your browser and log in:")
    print("=" * 60)
    print(kite.login_url())
    print("\n  STEP 2 — After login, copy the full redirect URL and paste below.")
    print("=" * 60)

    raw = input("\nPaste the full redirect URL (or just the request_token): ").strip()
    if "request_token=" in raw:
        request_token = raw.split("request_token=")[1].split("&")[0]
    else:
        request_token = raw

    try:
        data = kite.generate_session(request_token, api_secret=KITE_API_SECRET)
        access_token = data["access_token"]
        log.info("Access token generated successfully!")

        # Auto-update keys.txt
        try:
            content = KEYS_FILE.read_text() if KEYS_FILE.exists() else ""
            if "KITE_ACCESS_TOKEN=" in content:
                lines = content.splitlines()
                lines = [
                    f"KITE_ACCESS_TOKEN={access_token}" if l.startswith("KITE_ACCESS_TOKEN=") else l
                    for l in lines
                ]
                new_content = "\n".join(lines)
            else:
                new_content = content.rstrip() + f"\nKITE_ACCESS_TOKEN={access_token}\n"
            KEYS_FILE.write_text(new_content)
            log.info("keys.txt updated automatically.")
        except Exception as e:
            log.warning(f"Could not auto-update keys.txt: {e}")
            print(f"\n    KITE_ACCESS_TOKEN={access_token}\n")

    except Exception as e:
        log.error(f"Failed to generate session: {e}")


def get_nfo_instruments(state: BotState) -> pd.DataFrame:
    """
    Get NFO instruments list with daily caching.

    PERFORMANCE FIX: Previously called 6-10 times per scan.
    Now cached for the entire trading day.
    """
    today = datetime.date.today()
    if state._instruments_cache is not None and state._instruments_date == today:
        return state._instruments_cache

    if not state.kite:
        return pd.DataFrame()

    try:
        df = pd.DataFrame(state.kite.instruments("NFO"))
        state._instruments_cache = df
        state._instruments_date = today
        log.debug(f"NFO instruments cached: {len(df)} instruments")
        return df
    except Exception as e:
        log.error(f"Failed to fetch NFO instruments: {e}")
        return state._instruments_cache if state._instruments_cache is not None else pd.DataFrame()


def get_futures_token(state: BotState, symbol: str) -> int:
    """
    Look up the active futures instrument token for a symbol.
    Uses cached instruments. Auto-switches to next month if ≤7 days to expiry.
    Returns instrument_token (int), or 0 on failure.
    """
    try:
        instruments = get_nfo_instruments(state)
        if instruments.empty:
            return 0

        today = datetime.date.today()
        mask = (instruments["name"] == symbol) & (instruments["instrument_type"] == "FUT")
        futs = instruments[mask].copy()
        futs["expiry"] = pd.to_datetime(futs["expiry"]).dt.date
        futs = futs[futs["expiry"] >= today].sort_values("expiry")

        if futs.empty:
            return 0

        nearest = futs.iloc[0]
        days_to_exp = (nearest["expiry"] - today).days
        chosen = futs.iloc[1] if (days_to_exp <= 7 and len(futs) > 1) else nearest
        return int(chosen["instrument_token"])
    except Exception:
        return 0


@retry_on_failure(max_retries=2, base_delay=1.5, logger_name="Kite")
def fetch_quotes(state: BotState, keys: list) -> dict:
    """Fetch quotes with retry logic. Keys can be instrument tokens or strings."""
    if not state.kite:
        return {}
    return state.kite.quote(keys)


@retry_on_failure(max_retries=2, base_delay=1.5, logger_name="Kite")
def fetch_historical(state: BotState, token: int, from_date, to_date, interval: str) -> list:
    """Fetch historical candles with retry logic."""
    if not state.kite:
        return []
    return state.kite.historical_data(
        instrument_token=token,
        from_date=from_date,
        to_date=to_date,
        interval=interval,
    ) or []


def fetch_spot_price(state: BotState, symbol: str) -> float:
    """Fetch real-time spot price for an index symbol."""
    key = SPOT_QUOTE_KEYS.get(symbol)
    if not key:
        return 0.0
    try:
        q = fetch_quotes(state, [key])
        return q[key]["last_price"] if q and key in q else 0.0
    except Exception:
        return 0.0
