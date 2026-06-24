from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from plutus.config.settings import Settings, get_settings
from plutus.db.session import session_scope


def get_db() -> Iterator[Session]:
    """Session dependency. Overridden in tests via app.dependency_overrides."""
    with session_scope() as session:
        yield session


def get_app_settings() -> Settings:
    return get_settings()
