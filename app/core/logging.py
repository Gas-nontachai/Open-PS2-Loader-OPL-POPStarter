from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.core.constants import APP_NAME, APP_VERSION
from app.core.paths import logs_dir


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("ps2_toolkit")
    if logger.handlers:
        return logger
    directory = logs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / "application.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("Starting %s version %s", APP_NAME, APP_VERSION)
    return logger
