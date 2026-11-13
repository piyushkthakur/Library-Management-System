"""Configuration loading (Volume 3, Chapter 20).

Secrets and connection parameters are loaded from a local .env file via
python-dotenv; institution-adjustable operational parameters live in the
settings table and are read through SettingsRepository instead.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Settings-table keys and their seeded defaults (Volume 4, Chapter 14.2).
# Login lockout parameters (FR-AUTH-09) were added as configurable settings
# per the user-confirmed decision of 5 failures / 15-minute window / 15-minute
# lockout.
SETTING_LOAN_PERIOD_DAYS = "loan_period_days"
SETTING_FINE_ENABLED = "fine_enabled"
SETTING_FINE_RATE_PER_DAY = "fine_rate_per_day"
SETTING_OTP_EXPIRY_MINUTES = "otp_expiry_minutes"
SETTING_SMTP_HOST = "smtp_host"
SETTING_SMTP_PORT = "smtp_port"
SETTING_PASSWORD_MIN_LENGTH = "password_min_length"
SETTING_LOGIN_MAX_ATTEMPTS = "login_max_attempts"
SETTING_LOGIN_LOCKOUT_MINUTES = "login_lockout_minutes"
SETTING_LOGIN_WINDOW_MINUTES = "login_window_minutes"


def get_data_dir() -> Path:
    """Return the writable per-installation data directory for .env and logs
    (Volume 3, Chapter 27.2) — distinct from the read-only PyInstaller bundle."""
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    data_dir = base / "LibraryManagementSystem"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return get_data_dir()
    return Path(__file__).resolve().parent.parent.parent


def _env_path() -> Path:
    """Return the active .env path: project root in development, the data
    directory when packaged (Volume 3, Chapter 27.2)."""
    candidates = [_project_root() / ".env", get_data_dir() / ".env"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return _project_root() / ".env"


def load_environment() -> None:
    """Load .env from the project root (development) or the data directory
    (packaged). Credentials are never hard-coded (Volume 1, Chapter 28)."""
    load_dotenv(_env_path(), override=False)


def persist_env(name: str, value: str) -> None:
    """Write or update a variable in the active .env file, preserving other
    entries (Volume 2, Chapter 22 — SMTP credential storage). The value is
    never logged."""
    path = _env_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = f"{name}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            break
    else:
        lines.append(f"{prefix}{value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_env(name: str, default: str = "") -> str:
    """Return an environment variable value, defaulting when absent."""
    return os.environ.get(name, default)
