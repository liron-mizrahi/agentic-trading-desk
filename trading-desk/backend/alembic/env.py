"""
Alembic environment configuration.

Loads the ORM model metadata so that ``alembic revision --autogenerate`` can
detect schema changes automatically.  The database URL is pulled from
the ``DATABASE_URL`` environment variable (with a sensible default).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import Base so that Alembic sees all tables registered by our models.
from app.database import Base
from app.models import (  # noqa: F401 – model imports register tables on Base
    AnalysisLog,
    Trade,
)

# Alembic Config object, which provides access to values within the .ini file.
config = context.config

# Override the sqlalchemy.url from the environment so we honour DATABASE_URL.
config.set_main_option(
    "sqlalchemy.url",
    os.getenv(
        "DATABASE_URL",
        "postgresql://admin:tradingdesk@db:5432/trading_desk",
    ),
)

# Set up Python logging from the ini file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The target metadata for autogenerate support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well.  By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the SQL to the script output.
    """
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
    """Run migrations in 'online' mode – an engine is created and
    the database is migrated directly."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
