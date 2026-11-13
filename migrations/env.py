"""Alembic environment (Volume 4, Chapter 32).

Reads the database URL from .env through app.core.config, matching the
runtime configuration exactly, and targets the application's declarative
Base metadata so models and migrations can never drift apart.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_env, load_environment
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

load_environment()
config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("LMS_DB_URL")
    or (
        f"mysql+pymysql://{get_env('DB_USER', 'root')}:{get_env('DB_PASSWORD')}"
        f"@{get_env('DB_HOST', 'localhost')}:{get_env('DB_PORT', '3306')}"
        f"/{get_env('DB_NAME', 'lms_db')}?charset=utf8mb4"
    ),
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
