"""File-based session persistence for auto-login across restarts."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.config import get_data_dir
from app.core.database import Database
from app.core.security import SessionContext
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

_SESSION_FILE = "session.json"


def _session_path() -> Path:
    return get_data_dir() / _SESSION_FILE


def save_session(ctx: SessionContext) -> None:
    """Persist the session to disk."""
    data = {
        "user_id": ctx.user_id,
        "role": ctx.role,
        "full_name": ctx.full_name,
        "email": ctx.email,
    }
    _session_path().write_text(json.dumps(data), encoding="utf-8")


def load_session(database: Database) -> SessionContext | None:
    """Load a saved session, returning None if stale or invalid."""
    path = _session_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ctx = SessionContext(
            user_id=data["user_id"],
            role=data["role"],
            full_name=data["full_name"],
            email=data["email"],
        )
    except (json.JSONDecodeError, KeyError):
        clear_session()
        return None
    # Verify user still exists and is active
    user_repo = UserRepository()
    with database.session_scope() as session:
        user = user_repo.get_by_email(session, ctx.email)
        if user is None or not user.is_active:
            clear_session()
            return None
    return ctx


def clear_session() -> None:
    """Remove the saved session file."""
    path = _session_path()
    if path.exists():
        path.unlink()
