"""Settings model — settings key-value table (Volume 4, Chapter 14)."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Settings(Base):
    """Maps to the settings key-value table (Volume 4, Chapter 14)."""

    __tablename__ = "settings"

    setting_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    setting_value: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate="CURRENT_TIMESTAMP"
    )
