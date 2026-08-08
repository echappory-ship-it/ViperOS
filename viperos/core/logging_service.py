"""
logging_service.py - ViperOS's first real critical service.

Sets up structured, persistent logging for the whole session: rotating
log file under LOG_DIR, plus console output. Every other piece of
ViperOS (session.py, registry.py, modman.py callers) should get its
logger via get_logger(name) rather than using print() directly, once
this service has started.

This is critical, not modman-managed, because if logging itself is
broken, we want that loud and fatal at boot - not silently falling back
- since a system that can't log can't be debugged when something else
goes wrong.
"""

import logging
import logging.handlers
import os
from pathlib import Path

from viperos.core import config

# Overridable for local/dev testing, same pattern as modman's MODMAN_ROOT.
LOG_DIR = Path(os.environ.get("VIPEROS_LOG_DIR", "/var/log/viperos"))
LOG_FILE = LOG_DIR / "viperos.log"

LOGGER_NAME = "viperos"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 5 MB per file, keep 3 old ones - modest defaults for a system log.
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3

_configured = False


def start() -> None:
    """
    Critical-service entrypoint: configure the root 'viperos' logger.
    Registered with registry.py after config and state_dirs - reads its
    log level from config.get_config(), and assumes LOG_DIR already
    exists (state_dirs' job).
    """
    global _configured

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_level_name = config.get_config()["logging"]["level"]
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(log_level)
    logger.propagate = False

    # Avoid stacking duplicate handlers if start() is somehow called twice
    # (e.g. re-run in a test) - keep it idempotent.
    if _configured:
        logger.info("logging_service.start() called again - already configured, skipping.")
        return

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _configured = True
    logger.info(f"Logging initialized at level {log_level_name.upper()}. Writing to {LOG_FILE}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a given component, nested under the 'viperos'
    namespace (e.g. get_logger('modman') -> 'viperos.modman'). Safe to
    call before start() - Python's logging just won't have handlers
    attached yet, so messages are dropped rather than erroring, but
    every real caller should only need this after the logging critical
    service has started.
    """
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
