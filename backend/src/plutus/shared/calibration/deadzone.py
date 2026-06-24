from __future__ import annotations

from typing import Literal

from plutus.config.settings import Settings


def is_in_soft_dead_zone(score: int, settings: Settings) -> bool:
    return settings.soft_dead_zone_lower <= score <= settings.soft_dead_zone_upper


def deadzone_label(
    score: int, settings: Settings
) -> Literal["BUY_WATCH", "BUY", "WATCH"]:
    """B17 display-label resolver used by the dashboard signals window.

    WATCH below the dead zone, BUY_WATCH inside it, BUY above it.
    """
    if score < settings.soft_dead_zone_lower:
        return "WATCH"
    if is_in_soft_dead_zone(score, settings):
        return "BUY_WATCH"
    return "BUY"
