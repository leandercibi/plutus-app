from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from plutus.config import settings

# Use different engine parameters for SQLite vs PostgreSQL
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(settings.DATABASE_URL)
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model in plutus.db.models."""

    pass


def get_db():
    """FastAPI dependency: yields a session and closes it on request teardown."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
