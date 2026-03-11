"""
core/state.py — BotState dataclass.

All mutable runtime state is encapsulated here instead of module-level globals.

CHANGES (Phase 1 Rank 1):
  - last_spot:              cache of most-recently fetched spot per symbol
  - next_expiry_data:       cached next-expiry chain per symbol (refreshed ~15 min)
  - next_expiry_scan_tick:  per-symbol counter to gate next-expiry refresh
  - seeded_candles:         pre-market candle seed store {symbol: [candles]}
  - india_vix:              latest India VIX value fetched via Yahoo Finance
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BotState:
    """Encapsulates all mutable runtime state for the bot."""

    # Kite Connect instance (set after login)
    kite: Optional[object] = None

    # OI snapshots for delta computation
    prev_oi_snapshot:    dict = field(default_factory=dict)   # {symbol: {strike: {CE:oi, PE:oi}}}
    hour_oi_snapshot:    dict = field(default_factory=dict)
    prevday_oi_snapshot: dict = field(default_factory=dict)
    hour_snapshot_time:  dict = field(default_factory=dict)   # {symbol: datetime}

    # Spot price cache (updated every scan, reused by next-expiry fetch)
    last_spot: dict = field(default_factory=dict)             # {symbol: float}

    # Next-expiry chain cache — refreshed every NEXT_EXPIRY_REFRESH_SCANS scans
    next_expiry_data:      dict = field(default_factory=dict) # {symbol: chain_dict}
    next_expiry_scan_tick: dict = field(default_factory=dict) # {symbol: int} — scan counter

    # Pre-market candle seed (loaded at 08:45, used by technicals + VWAP)
    seeded_candles: dict = field(default_factory=dict)        # {symbol: [candle_dicts]}

    # India VIX (updated every scan via Yahoo Finance)
    india_vix: float = 0.0

    # Signal state
    prev_pcr: dict = field(default_factory=dict)              # {symbol: float}

    # Alert cooldowns: {(symbol, strike, side): scans_remaining}
    alert_cooldown: dict = field(default_factory=dict)

    # EOD state
    prev_day_data: dict  = field(default_factory=dict)        # {symbol: {pcr, max_pain, sr_levels, spot}}
    eod_captured:  bool  = False

    # Instrument cache (loaded once per day)
    _instruments_cache: object = None    # pd.DataFrame
    _instruments_date:  object = None    # datetime.date

    # Scan counter for heartbeat + next-expiry gating
    scan_count:      int    = 0
    last_heartbeat:  object = None       # datetime

    def reset_daily(self):
        """Reset state for a new trading day."""
        self.eod_captured = False
        self.alert_cooldown.clear()
        self.prev_oi_snapshot.clear()
        self.hour_oi_snapshot.clear()
        self.hour_snapshot_time.clear()
        self.prev_pcr.clear()
        self.next_expiry_data.clear()
        self.next_expiry_scan_tick.clear()
        self.seeded_candles.clear()
        self.last_spot.clear()
        self.india_vix = 0.0
        self.scan_count = 0
        self._instruments_cache = None
        self._instruments_date  = None
