"""
Agent Layer database utilities — sync SQLAlchemy for Celery worker use.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from agent.config import DATABASE_URL
from agent.models import Base

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Create all tables (called once on worker start)."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Return a new sync DB session."""
    return SessionLocal()
