"""Repository implementations (Volume 3, Chapter 12).

Repositories accept an active session from the Service Layer so that
multi-repository operations commit atomically (Volume 3, Chapter 13.2).
"""

from app.repositories.base import BaseRepository
from app.repositories.book_repository import BookRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.otp_repository import OtpRepository
from app.repositories.settings_repository import SettingsRepository
from app.repositories.teacher_issue_repository import TeacherIssueRepository
from app.repositories.teacher_repository import TeacherRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.user_repository import UserRepository

__all__ = [
    "BaseRepository",
    "BookRepository",
    "CategoryRepository",
    "OtpRepository",
    "SettingsRepository",
    "TeacherIssueRepository",
    "TeacherRepository",
    "TransactionRepository",
    "UserRepository",
]
