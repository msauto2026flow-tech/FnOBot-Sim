"""
data/fii_dii.py — FII/DII data fetcher and Excel logger.

PHASE 1 RANK 1 (Comment #12):
  Fetches FII/DII provisional data from NSE India at 19:30 IST.
  NSE publishes provisional data at https://www.nseindia.com/api/fiidiiTradeReact
  (JSON endpoint, no geo-block on this API unlike main site).

  Saves to FII_DII sheet in daily MarketData Excel file.
  Falls back to a secondary source (Investing.com scrape) if NSE API fails.
"""

import datetime
import json
import urllib.request

from config.settings import IST
from utils.logger import log

# NSE provisional FII/DII API — returns JSON with today's data
_NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":         "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":        "https://www.nseindia.com/market-data/fii-dii-activity",
}


def fetch_fii_dii() -> dict:
    """
    Fetch today's FII/DII provisional data from NSE India API.

    Returns dict:
        {
          "date":          "2026-03-11",
          "fii_net":       -1234.56,   # crores, negative = net sell
          "fii_buy":        9876.54,
          "fii_sell":      11111.10,
          "dii_net":        2345.67,
          "dii_buy":        8765.43,
          "dii_sell":       6419.76,
          "source":        "NSE",
          "fetched_at":    "19:31 IST",
        }
    Returns {"error": "..."} on failure.
    """
    try:
        req = urllib.request.Request(_NSE_FII_DII_URL, headers=_NSE_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

        # NSE returns a list; each item has category + buy/sell/net values
        fii_row = next((r for r in data if "FII" in r.get("category", "").upper()), None)
        dii_row = next((r for r in data if "DII" in r.get("category", "").upper()), None)

        if not fii_row or not dii_row:
            raise ValueError(f"Unexpected NSE response shape: {list(data[0].keys()) if data else 'empty'}")

        def _f(row, key, fallback=0.0):
            try:
                return float(str(row.get(key, fallback)).replace(",", ""))
            except (ValueError, TypeError):
                return fallback

        now_ist    = datetime.datetime.now(IST)
        today_str  = now_ist.date().isoformat()
        fetched_at = now_ist.strftime("%H:%M IST")

        result = {
            "date":       today_str,
            "fii_buy":    _f(fii_row, "buyValue"),
            "fii_sell":   _f(fii_row, "sellValue"),
            "fii_net":    _f(fii_row, "netValue"),
            "dii_buy":    _f(dii_row, "buyValue"),
            "dii_sell":   _f(dii_row, "sellValue"),
            "dii_net":    _f(dii_row, "netValue"),
            "source":     "NSE",
            "fetched_at": fetched_at,
        }
        log.info(
            f"[FII/DII] FII Net: ₹{result['fii_net']:,.2f} Cr  "
            f"DII Net: ₹{result['dii_net']:,.2f} Cr  (source: NSE)"
        )
        return result

    except Exception as e:
        log.warning(f"[FII/DII] NSE fetch failed: {e} — trying fallback")
        return _fetch_fii_dii_fallback()


def _fetch_fii_dii_fallback() -> dict:
    """
    Fallback: parse from moneycontrol FII/DII page.
    Returns same dict shape as fetch_fii_dii() with source="fallback" or {"error": ...}.
    """
    try:
        url = "https://www.moneycontrol.com/stocks/marketstats/fii_dii_activity/index.php"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Quick extract: look for FII/DII net values in the HTML table
        import re
        numbers = re.findall(r"[\-\+]?\d{1,6},?\d{3}(?:\.\d+)?", html)
        floats  = [float(n.replace(",", "")) for n in numbers[:20]]

        if len(floats) < 6:
            raise ValueError("Not enough numbers in fallback HTML")

        now_ist   = datetime.datetime.now(IST)
        return {
            "date":       now_ist.date().isoformat(),
            "fii_buy":    floats[0], "fii_sell": floats[1], "fii_net": floats[0] - floats[1],
            "dii_buy":    floats[3], "dii_sell": floats[4], "dii_net": floats[3] - floats[4],
            "source":     "fallback",
            "fetched_at": now_ist.strftime("%H:%M IST"),
        }
    except Exception as e:
        log.error(f"[FII/DII] Fallback also failed: {e}")
        return {"error": str(e)}


def build_fii_dii_telegram(fii_dii: dict) -> str:
    """Format FII/DII data as a Telegram HTML message block."""
    if not fii_dii or fii_dii.get("error"):
        return "📊 <b>FII/DII:</b> Data unavailable today"

    fii_net = fii_dii.get("fii_net", 0)
    dii_net = fii_dii.get("dii_net", 0)
    fii_e   = "🟢" if fii_net > 0 else "🔴"
    dii_e   = "🟢" if dii_net > 0 else "🔴"

    return (
        f"📊 <b>FII / DII Activity — {fii_dii.get('date', '—')}</b>\n"
        f"\n"
        f"{fii_e} FII Net: <b>₹{fii_net:,.2f} Cr</b>  "
        f"(Buy: {fii_dii.get('fii_buy',0):,.0f} / Sell: {fii_dii.get('fii_sell',0):,.0f})\n"
        f"{dii_e} DII Net: <b>₹{dii_net:,.2f} Cr</b>  "
        f"(Buy: {fii_dii.get('dii_buy',0):,.0f} / Sell: {fii_dii.get('dii_sell',0):,.0f})\n"
        f"\n"
        f"<i>Source: {fii_dii.get('source','—')} · Fetched {fii_dii.get('fetched_at','—')}</i>"
    )
