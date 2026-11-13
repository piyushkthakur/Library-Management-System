"""Structured exception hierarchy (Volume 3, Chapter 23).

Service-layer exceptions carry a pre-composed, user-safe message string;
no message surfaced to the Presentation Layer contains a table name, column
name, SQL fragment, or file path (Volume 3, Chapter 23.3).
"""


class LmsError(Exception):
    """Base class for all application exceptions."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnauthorizedOperationError(LmsError):
    """Acting user's role does not permit the requested operation (Ch. 15)."""


class ValidationError(LmsError):
    """A business rule or cross-field validation fails (Volume 3, Ch. 22.2)."""


class DuplicateResourceError(LmsError):
    """A uniqueness constraint is violated at the business level."""


class ResourceInUseError(LmsError):
    """A delete is blocked by a referential business rule."""


class InsufficientAvailabilityError(LmsError):
    """An issue is attempted against a book with zero available copies."""


class OtpVerificationError(LmsError):
    """An OTP is expired, already used, or does not match the latest code."""


class AccountLockedError(LmsError):
    """Login attempted against an account in a lockout window (FR-AUTH-09)."""


class DatabaseConnectivityError(LmsError):
    """MySQL is unreachable at startup or during an in-flight operation."""


class IntegrityConstraintError(LmsError):
    """A database-level constraint rejects a write."""


class RecordNotFoundError(LmsError):
    """A lookup by primary key or unique field returns no result."""
