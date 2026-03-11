"""
core/scheduler.py — Market hours checking and schedule management.

Improvements over v4:
  - Holiday-aware (checks NSE calendar)
  - Timezone-explicit (all comparisons in IST)
  - Graceful shutdown handling
"""

import datetime
import signal
import sys

from config.settings import IST
from config.holidays import is_trading_holiday
from utils.logger import log


def is_market_open() -> bool:
    """Check if NSE is currently open (9:15 - 15:30 IST, weekdays, non-holidays)."""
    now = datetime.datetime.now(IST)
    if now.weekday() >= 5:
        return False
    if is_trading_holiday(now.date()):
        return False
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


def is_pre_market_window() -> bool:
    """Check if we're in the pre-market window (8:45 - 9:15 IST)."""
    now = datetime.datetime.now(IST)
    if now.weekday() >= 5 or is_trading_holiday(now.date()):
        return False
    pre_open = now.replace(hour=8, minute=45, second=0, microsecond=0)
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    return pre_open <= now < market_open


def setup_graceful_shutdown(state, telegram_fn=None):
    """Register signal handlers for graceful shutdown."""
    def handler(signum, frame):
        log.info("Shutdown signal received. Cleaning up...")
        if telegram_fn:
            try:
                telegram_fn("🔴 <b>Bot shutting down</b> — manual stop or system exit.")
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
