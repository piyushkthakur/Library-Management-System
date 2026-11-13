"""Centralized logging configuration (Volume 3, Chapter 24).

Logs are written to a rotating file in the application's writable data
directory. No log entry ever includes a plaintext password, OTP code, or
SMTP credential (Volume 3, Chapter 24.2).
"""

import logging
from logging.handlers import RotatingFileHandler

from .config import get_data_dir, get_env

_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def _level() -> int:
    if get_env("APP_ENV", "development") == "development":
        return logging.DEBUG
    return logging.INFO


def setup_logging() -> None:
    """Configure the root logger once per process."""
    root = logging.getLogger()
    if getattr(root, "_lms_configured", False):
        return
    root.setLevel(_level())
    handler = RotatingFileHandler(
        get_data_dir() / "lms.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    root._lms_configured = True  # type: ignore[attr-defined]
