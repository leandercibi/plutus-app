from __future__ import annotations

from plutus.config.settings import Settings


def is_in_soft_dead_zone(score: int, settings: Settings) -> bool:
    return settings.soft_dead_zone_lower <= score <= settings.soft_dead_zone_upper
