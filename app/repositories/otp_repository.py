"""OtpRepository — password_reset_otps aggregate root (Volume 3, Chapter 12;
Volume 4, Chapter 13)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.password_reset_otp import PasswordResetOtp
from app.repositories.base import BaseRepository
from app.repositories.interfaces import OtpRepositoryInterface


class OtpRepository(BaseRepository, OtpRepositoryInterface):
    """Data access for the password_reset_otps table."""

    def create(
        self,
        session: Session,
        user_id: int,
        otp_code_hash: str,
        expires_at: datetime,
    ) -> PasswordResetOtp:
        try:
            record = PasswordResetOtp(
                user_id=user_id,
                otp_code_hash=otp_code_hash,
                expires_at=expires_at,
            )
            session.add(record)
            session.flush()
            return record
        except Exception as error:
            raise self._translate(error)

    def get_latest_unexpired(
        self, session: Session, user_id: int
    ) -> PasswordResetOtp | None:
        try:
            return session.scalar(
                select(PasswordResetOtp)
                .where(
                    PasswordResetOtp.user_id == user_id,
                    PasswordResetOtp.is_used.is_(False),
                    PasswordResetOtp.expires_at > datetime.now(),
                )
                .order_by(PasswordResetOtp.created_at.desc())
                .limit(1)
            )
        except Exception as error:
            raise self._translate(error)

    def mark_used(self, session: Session, otp_id: int) -> None:
        try:
            record = session.get(PasswordResetOtp, otp_id)
            if record is not None:
                record.is_used = True
                session.flush()
        except Exception as error:
            raise self._translate(error)
