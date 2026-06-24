from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from plutus.swing.sentiment.types import Headline

Confidence = Literal["high", "medium", "low", "none"]


@dataclass(frozen=True)
class EntityMatch:
    confidence: Confidence
    matched_on: str


# NSE-listed company names / aliases -> symbol. Deterministic, extend as needed.
_ALIASES: dict[str, str] = {
    "larsen": "LARSEN",
    "l&t": "LARSEN",
    "larsen & toubro": "LARSEN",
    "infosys": "INFY",
    "reliance": "RELIANCE",
    "tata consultancy": "TCS",
}

# For ambiguous strings, context tokens decide which entity is meant.
# 'TCS' may mean Tata Consultancy Services (the listed symbol) or Tata
# Communications. Software/IT context -> the TCS symbol; telecom context -> not.
_AMBIGUOUS_CONTEXT: dict[str, dict[str, set[str]]] = {
    "TCS": {
        "for_symbol": {
            "it",
            "software",
            "services",
            "consultancy",
            "consulting",
            "tech",
        },
        "against_symbol": {
            "telecom",
            "communications",
            "broadband",
            "network",
            "fiber",
        },
    }
}


def _tokens(text: str) -> set[str]:
    return {t.strip(".,:;!?()\"'").lower() for t in text.split()}


class EntityResolver:
    def resolve(self, headline: Headline, symbol: str) -> EntityMatch:
        if symbol in headline.entities:
            return EntityMatch("high", "entity_list")

        text = f"{headline.title} {headline.body}"
        tokens = _tokens(text)
        upper = symbol.upper()

        if upper in _AMBIGUOUS_CONTEXT and upper.lower() in tokens:
            ctx = _AMBIGUOUS_CONTEXT[upper]
            has_for = bool(tokens & ctx["for_symbol"])
            has_against = bool(tokens & ctx["against_symbol"])
            if has_against and not has_for:
                return EntityMatch("low", "ambiguous_against_context")
            if has_for:
                return EntityMatch("high", "ambiguous_for_context")
            return EntityMatch("medium", "ambiguous_no_context")

        if upper.lower() in tokens:
            return EntityMatch("high", "exact_symbol")

        for alias, mapped in _ALIASES.items():
            if mapped == upper and alias in text.lower():
                return EntityMatch("high", f"alias:{alias}")

        return EntityMatch("none", "no_match")
