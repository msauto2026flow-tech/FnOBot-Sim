"""
config/holidays.py — NSE trading holiday calendar.

Updated annually from NSE's official circular.
The bot checks this before scanning to avoid wasted API calls on holidays.
"""

import datetime

# NSE Holidays 2026 (source: NSE circular, update annually)
# Format: datetime.date objects for fast lookup
NSE_HOLIDAYS_2026 = frozenset({
    datetime.date(2026, 1, 26),   # Republic Day
    datetime.date(2026, 2, 17),   # Mahashivratri
    datetime.date(2026, 3, 17),   # Holi
    datetime.date(2026, 3, 30),   # Id-ul-Fitr (Eid)
    datetime.date(2026, 4, 2),    # Ram Navami
    datetime.date(2026, 4, 3),    # Good Friday
    datetime.date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    datetime.date(2026, 5, 1),    # Maharashtra Day
    datetime.date(2026, 5, 25),   # Buddha Purnima
    datetime.date(2026, 6, 5),    # Eid-ul-Adha (Bakrid)
    datetime.date(2026, 7, 6),    # Muharram
    datetime.date(2026, 8, 15),   # Independence Day
    datetime.date(2026, 8, 19),   # Janmashtami
    datetime.date(2026, 9, 4),    # Milad-un-Nabi
    datetime.date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    datetime.date(2026, 10, 20),  # Dussehra
    datetime.date(2026, 11, 9),   # Diwali (Laxmi Puja)
    datetime.date(2026, 11, 10),  # Diwali (Balipratipada)
    datetime.date(2026, 11, 16),  # Guru Nanak Jayanti
    datetime.date(2026, 12, 25),  # Christmas
})

# Combine all years here as you add them
ALL_HOLIDAYS = NSE_HOLIDAYS_2026


def is_trading_holiday(date: datetime.date = None) -> bool:
    """Check if a given date is an NSE trading holiday."""
    if date is None:
        date = datetime.date.today()
    return date in ALL_HOLIDAYS


def next_trading_day(from_date: datetime.date = None) -> datetime.date:
    """Find the next trading day (skips weekends and holidays)."""
    if from_date is None:
        from_date = datetime.date.today()
    candidate = from_date + datetime.timedelta(days=1)
    while candidate.weekday() >= 5 or is_trading_holiday(candidate):
        candidate += datetime.timedelta(days=1)
    return candidate


def prev_trading_day(from_date: datetime.date = None) -> datetime.date:
    """Find the most recent previous trading day."""
    if from_date is None:
        from_date = datetime.date.today()
    candidate = from_date - datetime.timedelta(days=1)
    while candidate.weekday() >= 5 or is_trading_holiday(candidate):
        candidate -= datetime.timedelta(days=1)
    return candidate
