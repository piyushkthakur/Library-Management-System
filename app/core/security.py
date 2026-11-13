"""Security utilities: bcrypt hashing and the session context
(Volume 3, Chapters 14, 25).

AuthService.hash_password / verify_password wrap bcrypt exclusively; no
other component touches raw password bytes (Volume 3, Chapter 25).
OTP codes are generated via Python's cryptographically secure random module
and persisted only as hashes (Volume 1, Chapter 28; Volume 4, Chapter 13).
"""

import secrets
from dataclasses import dataclass

import bcrypt


class _Hasher:
    """Central bcrypt wrapper used by AuthService and OtpRepository flows."""

    def hash(self, plaintext: str) -> str:
        return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

    def verify(self, plaintext: str, stored_hash: str) -> bool:
        try:
            return bcrypt.checkpw(
                plaintext.encode("utf-8"), stored_hash.encode("utf-8")
            )
        except (ValueError, TypeError):
            return False


class OtpCode:
    """Cryptographically secure 6-digit OTP generation and hashing.

    The code is persisted as a bcrypt hash — the same hashing utility used
    for verification comparison (Volume 4, Chapter 13); plaintext codes are
    never stored or logged (Volume 3, Chapter 24.2).
    """

    @staticmethod
    def generate() -> str:
        return f"{secrets.randbelow(1000000):06d}"

    @staticmethod
    def digest(otp: str) -> str:
        return hasher.hash(otp)

    @staticmethod
    def matches(otp: str, stored_digest: str) -> bool:
        return hasher.verify(otp, stored_digest)


@dataclass(frozen=True)
class SessionContext:
    """Authenticated session value object (Volume 3, Chapter 14.2), passed
    explicitly to every Service method requiring attribution or
    authorization."""

    user_id: int
    role: str
    full_name: str
    email: str


hasher = _Hasher()
