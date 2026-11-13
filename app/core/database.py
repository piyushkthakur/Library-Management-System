"""SQLAlchemy engine/session factory and connectivity validation
(Volume 3, Chapter 13; Volume 4, Chapters 3, 36.2).

The engine and session factory are constructed once per process
(Factory/Singleton patterns, Volume 3, Chapter 32). Repositories accept an
active session from the Service Layer so that multi-repository operations
commit atomically within a single database transaction.
"""

import logging
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_env
from .exceptions import DatabaseConnectivityError

logger = logging.getLogger(__name__)


def _create_database_if_not_exists(engine_url: str) -> None:
    """Create the database if it doesn't exist, then run migrations.
    
    Tries root first (XAMPP default), then configured user.
    Migrations run with the same user that created the database.
    """
    from pathlib import Path
    from sqlalchemy import create_engine
    from urllib.parse import urlparse
    
    parsed = urlparse(engine_url)
    db_name = parsed.path.lstrip('/')
    host_port = parsed.netloc.rsplit('@', 1)[1]  # Extract host:port
    
    # Try root first (XAMPP default: root with no password)
    created = False
    migration_user = None
    migration_password = None
    for user, password in [("root", ""), ("root", get_env("DB_ROOT_PASSWORD", "")), 
                           (get_env("DB_USER", "root"), get_env("DB_PASSWORD", ""))]:
        try:
            url = f"mysql+pymysql://{user}:{password}@{host_port}/?charset=utf8mb4"
            temp_engine = create_engine(url)
            try:
                with temp_engine.connect() as conn:
                    conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"))
                    conn.commit()
                logger.info(f"Database '{db_name}' ensured (user: {user})")
                created = True
                migration_user = user
                migration_password = password
            finally:
                temp_engine.dispose()
            break
        except Exception as e:
            logger.debug(f"Cannot create database with user '{user}': {e}")
            continue
    
    if not created:
        logger.warning("Could not create database with any user, assuming it exists")
    
    # Run migrations with the user that has full privileges
    # (env.py overwrites sqlalchemy.url from .env, so we set env vars instead)
    try:
        from alembic.config import Config
        from alembic import command
        import os
        
        # Override env vars so migrations/env.py picks up privileged credentials
        if migration_user:
            os.environ["DB_USER"] = migration_user
            os.environ["DB_PASSWORD"] = migration_password or ""
        
        project_root = Path(__file__).resolve().parent.parent.parent
        alembic_ini = project_root / "alembic.ini"
        alembic_cfg = Config(str(alembic_ini))
        alembic_cfg.set_main_option("sqlalchemy.url", engine_url)
        alembic_cfg.set_main_option("script_location", str(project_root / "migrations"))
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations applied successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise  # Let caller handle migration failure


def _database_url() -> str:
    host = get_env("DB_HOST", "localhost")
    port = get_env("DB_PORT", "3306")
    name = get_env("DB_NAME", "lms_db")
    user = get_env("DB_USER", "root")
    password = get_env("DB_PASSWORD", "")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


class Database:
    """Owns the SQLAlchemy engine and session factory for the application."""

    def __init__(self, database_url: str | None = None) -> None:
        url = database_url or _database_url()
        self._engine: Engine = create_engine(
            url,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self._session_factory: sessionmaker[Session] = sessionmaker(
            bind=self._engine, expire_on_commit=False
        )

    @property
    def engine(self) -> Engine:
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        return self._session_factory

    def connectivity_ok(self) -> bool:
        """Probe MySQL connectivity (Volume 3, Chapter 13.3)."""
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def ensure_connectivity(self) -> None:
        """Validate MySQL connectivity at startup. Tries to start the service if down."""
        if not self.connectivity_ok():
            logger.info("MySQL not running, attempting to start...")
            _try_start_mysql()
            for _ in range(10):
                time.sleep(1)
                if self.connectivity_ok():
                    logger.info("MySQL started successfully")
                    break
                try:
                    _create_database_if_not_exists(str(self._engine.url))
                    if self.connectivity_ok():
                        break
                except Exception as e:
                    logger.error(f"Database setup failed: {e}")
            else:
                raise DatabaseConnectivityError(
                    "Unable to connect to the database. Start MySQL manually and try again."
                )

        try:
            _create_database_if_not_exists(str(self._engine.url))
        except Exception as e:
            logger.error(f"Migration failed: {e}")

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Open one session per business operation (unit of work, Volume 3,
        Chapter 13.2): commit on success, rollback on any exception."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def __getstate__(self) -> dict[str, Any]:
        return {}

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__init__()


def _find_xampp_root() -> Path | None:
    """Locate XAMPP installation. Checks XAMPP_DIR env var, then common drives."""
    env = get_env("XAMPP_DIR")
    if env:
        p = Path(env)
        if (p / "mysql_start.bat").exists():
            return p
    for drive in "CDEFG":
        p = Path(f"{drive}:/xampp")
        if (p / "mysql_start.bat").exists():
            return p
    return None


def _try_start_mysql() -> None:
    """Attempt to start the MySQL service. Tries Windows service first, then XAMPP."""
    service_name = get_env("MYSQL_SERVICE_NAME", "MySQL")
    for name in [service_name, "MySQL80"]:
        try:
            result = subprocess.run(
                ["net", "start", name],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                logger.info("Started MySQL service: %s", name)
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    # ponytail: XAMPP fallback — use the batch script that ships with XAMPP
    xampp_root = _find_xampp_root()
    if xampp_root:
        bat = xampp_root / "mysql_start.bat"
        try:
            subprocess.Popen(
                ["cmd", "/c", str(bat)],
                cwd=str(xampp_root),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            logger.info("Launched XAMPP MySQL via %s", bat)
            return
        except Exception as exc:
            logger.warning("Failed to start XAMPP MySQL: %s", exc)
    logger.warning("Could not start MySQL automatically")
