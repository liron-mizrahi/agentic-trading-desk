"""SQLAlchemy engine, session factories, and declarative base.

Engines are created lazily (first use), not at import time, so
the module can be imported without a live database connection
(for testing, type checking, etc.).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Base for all ORM models."""
    pass


# ── Lazy engine factories ──────────────────────────────────────────────────

_sync_engine = None
_async_engine = None
_async_sessionmaker = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            echo=settings.DEBUG,
        )
    return _sync_engine


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            settings.DATABASE_URL_ASYNC,
            pool_pre_ping=True,
            echo=settings.DEBUG,
        )
    return _async_engine


def _get_async_sessionmaker():
    global _async_sessionmaker
    if _async_sessionmaker is None:
        _async_sessionmaker = async_sessionmaker(
            bind=_get_async_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _async_sessionmaker


def get_session_sync():
    """Return a synchronous SQLAlchemy session (for non-async endpoints)."""
    from sqlalchemy.orm import Session, sessionmaker
    engine = _get_sync_engine()
    return Session(engine)


async def init_db() -> None:
    """Create all tables on startup (dev convenience)."""
    engine = _get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose engine on shutdown."""
    global _async_engine, _sync_engine
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
    if _sync_engine:
        _sync_engine.dispose()
        _sync_engine = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async DB session."""
    async with _get_async_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
