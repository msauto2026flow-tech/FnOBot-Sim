"""
config/settings.py - Single source of truth for all configuration.

Reads from environment variables (.env file) with sensible defaults.
Every other module imports paths, thresholds, and constants from here.

CHANGES (Phase 1 Rank 1):
  - DATA_DIR now points to Desktop/Market Data (not FnOBot subfolder)
  - OI spike thresholds recalibrated for 3-min intervals: 8% / 15%
  - All schedule times confirmed and wired
  - INDIA_VIX_YAHOO_TICKER confirmed
  - NEXT_EXPIRY_REFRESH_SCANS: next expiry tab refreshes every 15 min (5 scans x 3 min)
"""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

# Load .env file if present
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass  # python-dotenv not installed; rely on system env vars

# =============================================================================
#  PATHS  (forward slashes - pathlib handles them fine on Windows)
# =============================================================================

BASE_DIR = Path(os.environ.get(
    "FNOBOT_BASE_DIR",
    "C:/Users/marut/Desktop/FnOBot"
))
DATA_DIR = Path(os.environ.get(
    "FNOBOT_DATA_DIR",
    "C:/Users/marut/Desktop/Market Data"
))
KEYS_FILE = Path(os.environ.get(
    "FNOBOT_KEYS_FILE",
    "C:/Users/marut/Desktop/keys.txt"
))
DASHBOARD_DIR = BASE_DIR / "Dashboard"

# Archive folder for dated EOD dashboards: dashboard_YYYY-MM-DD.html
DASHBOARD_ARCHIVE_DIR = DATA_DIR / "DashboardArchive"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
DASHBOARD_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
#  TIMEZONE
# =============================================================================

IST = ZoneInfo("Asia/Kolkata")

# =============================================================================
#  CREDENTIALS
# =============================================================================

def load_keys() -> dict:
    """Load key-value pairs from keys.txt file. Also merges env vars."""
    keys = {}
    if KEYS_FILE.exists():
        for line in KEYS_FILE.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                keys[k.strip()] = v.strip()
    # Environment overrides
    for k in ("KITE_API_KEY", "KITE_API_SECRET", "KITE_ACCESS_TOKEN",
              "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
        v = os.environ.get(k)
        if v:
            keys[k] = v
    return keys

_KEYS = load_keys()

KITE_API_KEY      = _KEYS.get("KITE_API_KEY", "")
KITE_API_SECRET   = _KEYS.get("KITE_API_SECRET", "")
KITE_ACCESS_TOKEN = _KEYS.get("KITE_ACCESS_TOKEN", "")
TELEGRAM_TOKEN    = _KEYS.get("TOKEN", "")
TELEGRAM_CHAT_ID  = _KEYS.get("CHAT_ID", "")

# =============================================================================
#  SCAN INTERVAL
# =============================================================================

SCAN_INTERVAL_MIN = int(os.environ.get("FNOBOT_SCAN_INTERVAL", "3"))

# =============================================================================
#  INDEX TOKENS (Kite instrument tokens for NSE indices)
# =============================================================================

INDEX_TOKENS = {
    "NIFTY":     256265,
    "BANKNIFTY": 260105,
}

SPOT_QUOTE_KEYS = {
    "NIFTY":     "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
}

# India VIX - fetched via Yahoo Finance (^INDIAVIX); NSE geo-blocks Germany
INDIA_VIX_YAHOO_TICKER = "^INDIAVIX"

# =============================================================================
#  OPTION CHAIN SETTINGS
# =============================================================================

STRIKES_AROUND_ATM = 10  # number of strikes above and below ATM to analyse

# OI Spike % thresholds - recalibrated for 3-min intervals (was 15%/25% for 15-min)
OI_SPIKE_PCT           = 8.0   # alert threshold for analyse_chain() spikes display
OI_DELTA_SPIKE_LOW     = 8.0   # SIGNIFICANT tier (was 15%)
OI_DELTA_SPIKE_HIGH    = 15.0  # EXTREME tier (was 25%)

# OI Delta Alert Cooldown (in scans, at 3-min each)
# EXTREME: 5 scans = 15 min | SIGNIFICANT: 10 scans = 30 min
OI_ALERT_COOLDOWN_EXTREME     = 5
OI_ALERT_COOLDOWN_SIGNIFICANT = 10
OI_ALERT_MIN_ABS_OI           = 50_000

OI_DELTA_STRIKES = 10  # strikes around ATM for delta computation

# Next-expiry tab refresh interval: every N scans (5 scans x 3 min = 15 min)
NEXT_EXPIRY_REFRESH_SCANS = 5

# =============================================================================
#  NIFTY 50 SYMBOLS
# =============================================================================

NIFTY50_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC",
    "KOTAKBANK", "LT", "SBIN", "AXISBANK", "BAJFINANCE", "BHARTIARTL", "ASIANPAINT",
    "HCLTECH", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "NESTLEIND", "WIPRO",
    "ONGC", "POWERGRID", "NTPC", "TATAMOTORS", "BAJAJ-AUTO", "JSWSTEEL", "TATASTEEL",
    "TECHM", "HINDALCO", "M&M", "BAJAJFINSV", "DRREDDY", "CIPLA", "APOLLOHOSP",
    "GRASIM", "INDUSINDBK", "EICHERMOT", "COALINDIA", "TATACONSUM", "ADANIENT",
    "ADANIPORTS", "BPCL", "SBILIFE", "HDFCLIFE", "DIVISLAB", "BRITANNIA",
    "SHREECEM", "UPL", "ZOMATO",
]

# =============================================================================
#  TECHNICAL INDICATOR PARAMETERS
# =============================================================================

# Phase 2 - Technicals
ST_PERIOD      = 10
ST_MULTIPLIER  = 3.0
EMA_PERIOD     = 20
RSI_PERIOD     = 14
DIV_LOOKBACK   = 5
HHLH_LOOKBACK  = 6

# Phase 4 - OI Concentration
WALL_THRESHOLD      = 2.5
TOP_N_CONCENTRATION = 3
PIN_DTE_STRONG      = 2
PIN_DTE_MODERATE    = 5
PIN_DISTANCE_TIGHT  = 0.3
PIN_DISTANCE_NEAR   = 0.8
SYMMETRY_WINDOW     = 3

# =============================================================================
#  RETRY / RESILIENCE SETTINGS
# =============================================================================

API_MAX_RETRIES    = 3
API_RETRY_DELAY    = 2      # seconds - doubles each retry (2, 4, 8)
HEARTBEAT_INTERVAL = 60     # minutes between heartbeat messages

# Scheduled task times (HH:MM IST)
PRE_MARKET_SEED_TIME    = "08:45"   # Fetch historical candles for indicator seeding
MARKET_OPEN_BRIEF_TIME  = "09:14"   # Morning pre-market brief (1 min before open)
EOD_SNAPSHOT_TIME       = "15:30"   # EOD data capture + Excel finalise + dashboard archive
POST_MARKET_BRIEF_TIME  = "15:45"   # Post-market Telegram brief + stop dashboard refresh
FII_DII_FETCH_TIME      = "19:30"   # FII/DII data fetch (NSE usually finalises ~19:30)
AUTO_TERMINATE_TIME     = "19:45"   # Auto-terminate bot after FII/DII fetch
DASHBOARD_STOP_REFRESH  = (15, 45)  # (hour, minute) IST - no auto-reload after this

# =============================================================================
#  EXCEL STYLING COLOURS
# =============================================================================

COLOUR_HEADER_DARK  = "1F3864"
COLOUR_HEADER_MID   = "2E75B6"
COLOUR_HEADER_LIGHT = "D6E4F0"
COLOUR_GREEN        = "E2EFDA"
COLOUR_RED          = "FCE4D6"
COLOUR_ORANGE       = "FFE699"
COLOUR_RED_DARK     = "C00000"
COLOUR_WHITE        = "FFFFFF"
COLOUR_GREY         = "F2F2F2"

# =============================================================================
#  GLOBAL MARKET TICKERS (Yahoo Finance)
# =============================================================================

GLOBAL_TICKERS = {
    "Dow Jones":  "%5EDJI",
    "Nasdaq":     "%5EIXIC",
    "S&P 500":    "%5EGSPC",
    "Nikkei 225": "%5EN225",
    "Hang Seng":  "%5EHSI",
    "Gift Nifty": "NIFTY50.NS",
} 
# ============================================================= 
#  SIGNAL THRESHOLDS 
# ============================================================= 
PCR_STRONG_BULL = 1.30 
PCR_MILD_BULL   = 1.10 
PCR_MILD_BEAR   = 0.85 
PCR_STRONG_BEAR = 0.70 
MAX_PAIN_GAP_PCT = 1.5 
ALERT_PCR_CROSS  = 1.20 
ALERT_PAIN_GAP   = 1.0 
