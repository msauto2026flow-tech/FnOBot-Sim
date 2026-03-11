"""
data/vix_fetcher.py — India VIX fetcher via Yahoo Finance.

PHASE 1 RANK 1 (OBJ 7 / OBJ 8 Task 2):
  NSE geo-blocks Germany for VIX. Yahoo Finance hosts ^INDIAVIX without
  geo-restriction. This module fetches it every scan via the yfinance library
  (or falls back to a direct Yahoo Finance v8 API call if yfinance unavailable).

  Result stored in BotState.india_vix and logged to VIX column in PCR_MAXPAIN
  Excel sheet.
"""

from utils.logger import log


def fetch_india_vix() -> float:
    """
    Fetch the latest India VIX value.
    Returns float (e.g. 13.45) or 0.0 on failure.

    Tries yfinance first (preferred), then raw Yahoo Finance JSON API.
    """
    vix = _fetch_via_yfinance()
    if vix > 0:
        return vix
    vix = _fetch_via_yahoo_json()
    if vix > 0:
        return vix
    log.warning("[VIX] Both fetch methods failed — returning 0.0")
    return 0.0


def _fetch_via_yfinance() -> float:
    try:
        import yfinance as yf
        ticker = yf.Ticker("^INDIAVIX")
        hist   = ticker.history(period="1d", interval="1m")
        if hist.empty:
            return 0.0
        vix = float(hist["Close"].iloc[-1])
        log.debug(f"[VIX] yfinance: {vix:.2f}")
        return round(vix, 2)
    except ImportError:
        return 0.0   # yfinance not installed; fall through to JSON fetch
    except Exception as e:
        log.debug(f"[VIX] yfinance error: {e}")
        return 0.0


def _fetch_via_yahoo_json() -> float:
    """Direct Yahoo Finance v8 quote API — no login required."""
    try:
        import urllib.request
        import json

        url     = "https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?interval=1m&range=1d"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        closes = (
            data.get("chart", {})
                .get("result", [{}])[0]
                .get("indicators", {})
                .get("quote", [{}])[0]
                .get("close", [])
        )
        # Get last non-None close
        valid = [c for c in closes if c is not None]
        if not valid:
            return 0.0
        vix = round(float(valid[-1]), 2)
        log.debug(f"[VIX] Yahoo JSON: {vix:.2f}")
        return vix
    except Exception as e:
        log.debug(f"[VIX] Yahoo JSON error: {e}")
        return 0.0
