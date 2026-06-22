from __future__ import annotations

from plutus.db.models import Base  # registers all ORM models including RunLogRow
from plutus.db.session import get_engine


def init_db() -> None:
    Base.metadata.create_all(get_engine())
