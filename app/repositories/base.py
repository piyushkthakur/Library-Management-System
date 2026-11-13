"""Base repository with data-layer exception translation
(Volume 3, Chapters 12-13, 23.2).

Repositories are stateless: each method receives an active session from the
Service Layer (Volume 3, Chapter 13.2; Volume 4, Chapter 28.2), enabling
atomic multi-repository operations. Repositories detect only data-integrity
conditions they are uniquely positioned to observe; business-rule
interpretation belongs to the Service Layer.
"""

import logging

from sqlalchemy.exc import IntegrityError, NoResultFound, OperationalError

from app.core.exceptions import (
    DatabaseConnectivityError,
    IntegrityConstraintError,
    RecordNotFoundError,
)

logger = logging.getLogger(__name__)


class BaseRepository:
    """Provides data-layer exception translation for repository methods."""

    def _translate(self, error: Exception) -> Exception:
        if isinstance(error, OperationalError):
            return DatabaseConnectivityError(
                "Unable to connect to the database. Check that MySQL is "
                "running and try again."
            )
        if isinstance(error, IntegrityError):
            logger.warning(
                "Integrity constraint violation: %s", error.orig.__class__.__name__
            )
            return IntegrityConstraintError(
                "The record conflicts with existing data and could not be saved."
            )
        if isinstance(error, NoResultFound):
            return RecordNotFoundError("The requested record was not found.")
        return error
