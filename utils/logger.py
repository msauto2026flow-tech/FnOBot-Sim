"""
utils/logger.py — Centralized logging configuration.

Replaces all bare print() statements with structured logging.
Outputs to both console and a daily rotating log file.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler


def setup_logger(
    name: str = "fnobot",
    log_dir: Path = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Configure and return the application logger.

    Args:
        name:    Logger name (use 'fnobot' for the main logger)
        log_dir: Directory for log files (None = console only)
        level:   Minimum log level

    Returns:
        Configured Logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on re-import
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler — always enabled
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler — daily rotation, keeps 30 days
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            filename=log_dir / "fnobot.log",
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Create the default application logger
# Other modules import this: from utils.logger import log
log = setup_logger("fnobot")
