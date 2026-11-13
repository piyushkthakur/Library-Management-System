"""Role guard helpers (Volume 3, Chapter 15.2).

Every Service method that requires role restriction begins with a guard
clause validating SessionContext.role against the permitted role set,
raising UnauthorizedOperationError before any further logic executes.
"""

from app.core.exceptions import UnauthorizedOperationError
from app.core.security import SessionContext
from app.models.user import UserRole


def require_role(context: SessionContext, allowed_roles: set[UserRole]) -> None:
    """Reject the operation when the acting user's role is not permitted."""
    if context.role not in {role.value for role in allowed_roles}:
        raise UnauthorizedOperationError(
            "You do not have permission to perform this action."
        )
