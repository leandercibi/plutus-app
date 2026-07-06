from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from plutus.config.settings import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().db_url, future=True)
    return _engine


def _session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_engine(), future=True
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    s = _session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def reset_engine_for_tests(url: str) -> None:
    """Test-only: rebind the engine to an isolated DB URL."""
    global _engine, _SessionLocal
    _engine = create_engine(url, future=True)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine, future=True)
