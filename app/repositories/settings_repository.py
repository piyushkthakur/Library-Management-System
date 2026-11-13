"""SettingsRepository — settings key-value aggregate root (Volume 3,
Chapter 12; Volume 4, Chapter 14)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.settings import Settings
from app.repositories.base import BaseRepository
from app.repositories.interfaces import SettingsRepositoryInterface


class SettingsRepository(BaseRepository, SettingsRepositoryInterface):
    """Data access for the settings table (FR-SET-02)."""

    def get_value(self, session: Session, key: str) -> str | None:
        try:
            record = session.get(Settings, key)
            return record.setting_value if record is not None else None
        except Exception as error:
            raise self._translate(error)

    def set_value(self, session: Session, key: str, value: str) -> None:
        try:
            record = session.get(Settings, key)
            if record is None:
                session.add(Settings(setting_key=key, setting_value=value))
            else:
                record.setting_value = value
            session.flush()
        except Exception as error:
            raise self._translate(error)

    def get_all(self, session: Session) -> dict[str, str]:
        try:
            return {
                record.setting_key: record.setting_value
                for record in session.scalars(select(Settings))
            }
        except Exception as error:
            raise self._translate(error)
