"""Maps backend exceptions to user-safe messages for toasts and dialogs.

The full exception hierarchy lives in :mod:`app.core.exceptions`; the UI
never surfaces raw exceptions, stack traces or SQL to the user.
"""

from __future__ import annotations

from app.core.exceptions import (
    AccountLockedError,
    DatabaseConnectivityError,
    DuplicateResourceError,
    InsufficientAvailabilityError,
    IntegrityConstraintError,
    LmsError,
    RecordNotFoundError,
    ResourceInUseError,
    UnauthorizedOperationError,
    ValidationError,
)
from app.presentation.shared_components.toast import ToastHost


def friendly_message(exc: Exception) -> str:
    """Human-readable message for any exception that reaches the UI."""
    if isinstance(exc, DatabaseConnectivityError):
        return "The database is unreachable. Check the server and try again."
    if isinstance(exc, IntegrityConstraintError):
        return "This record cannot be changed while other records depend on it."
    if isinstance(
        exc,
        (ValidationError, DuplicateResourceError, ResourceInUseError,
         InsufficientAvailabilityError, RecordNotFoundError,
         UnauthorizedOperationError, AccountLockedError, LmsError),
    ):
        return str(exc)
    return "Something went wrong. Please try again."


def notify_error(toast: ToastHost, exc: Exception) -> None:
    """Show a user-safe error toast for any exception that reaches the UI."""
    toast.show(friendly_message(exc), "error")