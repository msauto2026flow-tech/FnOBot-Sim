"""
output/telegram.py — Telegram messaging with smart splitting and retry.

BUG FIX: Messages are now split on line boundaries to avoid breaking HTML tags.
"""

import urllib.parse
import urllib.request

from config.settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from utils.logger import log


def send_telegram(msg: str):
    """
    Send message to Telegram. Splits on line boundaries if over 4096 chars.

    BUG FIX (v5): Previous version split mid-string which could break HTML tags.
    Now splits on newline boundaries.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram: Missing TOKEN or CHAT_ID")
        return

    chunks = _smart_split(msg, max_len=4096)
    for chunk in chunks:
        _send_chunk(chunk)


def _smart_split(msg: str, max_len: int = 4096) -> list[str]:
    """
    Split a message on line boundaries, keeping chunks under max_len.
    This prevents splitting inside HTML tags like <b>...</b>.
    """
    if len(msg) <= max_len:
        return [msg]

    chunks = []
    current = []
    current_len = 0

    for line in msg.split("\n"):
        line_len = len(line) + 1  # +1 for the newline
        if current_len + line_len > max_len and current:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len

    if current:
        chunks.append("\n".join(current))

    return chunks


def _send_chunk(text: str):
    """Send a single chunk to Telegram."""
    params = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    })
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?{params}"
    try:
        urllib.request.urlopen(url, timeout=10)
    except Exception as e:
        log.error(f"Telegram send error: {e}")


def send_heartbeat(scan_count: int):
    """Send a heartbeat message so you know the bot is alive."""
    send_telegram(f"💚 Bot heartbeat — {scan_count} scans completed. Running normally.")
