"""Quick token validity check — used by start_bot.bat"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import KITE_API_KEY, KITE_ACCESS_TOKEN

try:
    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=KITE_API_KEY)
    kite.set_access_token(KITE_ACCESS_TOKEN)
    kite.profile()
    print("TOKEN_VALID")
except Exception:
    print("TOKEN_EXPIRED")
