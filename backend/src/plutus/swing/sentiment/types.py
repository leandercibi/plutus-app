from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Headline:
    """A news headline consumed by the deterministic sentiment path.

    Kept self-contained in the sentiment package: the `data/news.py` adapter
    produces the same shape, but sentiment does not depend on it (A8 isolation).
    `entities` is populated by deterministic NER, never by the LLM.
    """

    source: str
    published_at: datetime
    title: str
    body: str
    entities: list[str] = field(default_factory=list)
