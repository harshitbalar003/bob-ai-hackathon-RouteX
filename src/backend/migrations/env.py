"""
Alembic migration environment.

Uses a synchronous SQLite engine (sqlite3 driver, not aiosqlite) because
Alembic's migration runner is synchronous.  The application runtime uses
aiosqlite via SQLAlchemy's async engine — these are two separate engines
talking to the same file.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Import our ORM so autogenerate can diff against it ───────────────────────
# This must come before target_metadata is set.
import app.models.orm  # noqa: F401  — registers all Table classes on Base
from app.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Use the synchronous SQLite URL derived from the async URL in alembic.ini.
# The ini file stores the sync URL; the app config stores the async URL.
def _get_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    # Fallback: derive from env
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./supply_chain.db")
    # Strip async driver prefix if present
    return db_url.replace("sqlite+aiosqlite", "sqlite")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without connecting)."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,   # Required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect and apply)."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,   # Required for SQLite ALTER TABLE support
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
