"""Logging setup for Kōan.

Logs to ~/.koan/koan.log. Debug level for file, warnings only for console.
"""

from __future__ import annotations

import logging
from pathlib import Path

_LOG_DIR = Path.home() / ".koan"
_LOG_FILE = _LOG_DIR / "koan.log"
_CONFIGURED = False


def setup_logging(verbose: bool = False):
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("koan")
    logger.setLevel(logging.DEBUG)

    # File handler — everything goes to log file
    fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # Console handler — only warnings/errors (or debug if verbose)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if verbose else logging.WARNING)
    ch.setFormatter(logging.Formatter("\033[90m%(levelname)s: %(message)s\033[0m"))
    logger.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"koan.{name}")
