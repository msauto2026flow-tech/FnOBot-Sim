"""
utils/helpers.py — Shared utility functions used across the codebase.
"""

import time
import functools
from utils.logger import log


def retry_on_failure(max_retries: int = 3, base_delay: float = 2.0, logger_name: str = "API"):
    """
    Decorator: retry a function on exception with exponential backoff.

    Args:
        max_retries: Number of retry attempts
        base_delay:  Initial delay in seconds (doubles each retry)
        logger_name: Label for log messages
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        log.warning(
                            f"[{logger_name}] {func.__name__} failed (attempt {attempt+1}/{max_retries+1}): {e}. "
                            f"Retrying in {delay:.0f}s..."
                        )
                        time.sleep(delay)
                    else:
                        log.error(f"[{logger_name}] {func.__name__} failed after {max_retries+1} attempts: {e}")
            return None
        return wrapper
    return decorator


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division that returns default on zero denominator."""
    return round(numerator / denominator, 6) if denominator else default


def format_number(value: float, decimals: int = 1) -> str:
    """Format a number with comma separators."""
    if decimals == 0:
        return f"{int(value):,}"
    return f"{value:,.{decimals}f}"
