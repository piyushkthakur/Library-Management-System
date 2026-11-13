"""Cross-cutting infrastructure: configuration loading, security utilities,
the exception hierarchy, and logging setup (Volume 3, Chapters 20, 22-25)."""

from .config import get_data_dir, get_env, persist_env
from .database import Database
from .exceptions import (
    AccountLockedError,
    DatabaseConnectivityError,
    DuplicateResourceError,
    InsufficientAvailabilityError,
    IntegrityConstraintError,
    OtpVerificationError,
    RecordNotFoundError,
    ResourceInUseError,
    UnauthorizedOperationError,
    ValidationError,
)
from .mailer import send_email
from .security import OtpCode, SessionContext, hasher

__all__ = [
    "AccountLockedError",
    "Database",
    "DatabaseConnectivityError",
    "DuplicateResourceError",
    "InsufficientAvailabilityError",
    "IntegrityConstraintError",
    "OtpCode",
    "OtpVerificationError",
    "RecordNotFoundError",
    "ResourceInUseError",
    "SessionContext",
    "UnauthorizedOperationError",
    "ValidationError",
    "get_data_dir",
    "get_env",
    "hasher",
    "persist_env",
    "send_email",
]
