from __future__ import annotations

from datetime import datetime

from plutus.swing.sentiment.entity_resolver import EntityResolver
from plutus.swing.sentiment.types import Headline


def _hl(title: str, body: str = "", entities: list[str] | None = None) -> Headline:
    return Headline(
        source="src.com",
        published_at=datetime(2024, 1, 1, 9, 0, 0),
        title=title,
        body=body,
        entities=entities if entities is not None else [],
    )


def test_exact_symbol_mention_is_high() -> None:
    r = EntityResolver()
    m = r.resolve(_hl("INFY surges 5% on strong results"), "INFY")
    assert m.confidence == "high"


def test_company_name_match_is_high() -> None:
    r = EntityResolver()
    m = r.resolve(_hl("Larsen wins record infrastructure order"), "LARSEN")
    assert m.confidence == "high"


def test_alias_lt_matches_larsen() -> None:
    r = EntityResolver()
    m = r.resolve(_hl("L&T bags new contract"), "LARSEN")
    assert m.confidence == "high"


def test_no_mention_is_none() -> None:
    r = EntityResolver()
    m = r.resolve(_hl("Reliance announces new energy venture"), "INFY")
    assert m.confidence == "none"


def test_tcs_context_disambiguates_consultancy() -> None:
    # TCS with software / IT context -> Tata Consultancy Services -> high for TCS symbol
    r = EntityResolver()
    m = r.resolve(_hl("TCS wins large IT software services deal"), "TCS")
    assert m.confidence == "high"


def test_tcs_context_disambiguates_communications_not_tcs_symbol() -> None:
    # TCS string but telecom/communications context -> Tata Communications, NOT TCS symbol
    r = EntityResolver()
    m = r.resolve(_hl("TCS telecom communications network expands broadband"), "TCS")
    assert m.confidence in ("low", "none", "medium")
    assert m.confidence != "high"


def test_explicit_entity_list_match_is_high() -> None:
    r = EntityResolver()
    m = r.resolve(_hl("Some firm in the news", entities=["INFY"]), "INFY")
    assert m.confidence == "high"
