from __future__ import annotations

import logging

from plutus.config.settings import get_settings


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=get_settings().log_level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    return logger
