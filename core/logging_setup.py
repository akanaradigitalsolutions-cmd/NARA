"""Central logging for NARA (Phase 8 — Hardening).

``setup_logging`` sends NARA's logs to a rotating file under ``logging.path``
(``~/.nara/logs/nara.log`` by default) so a crash leaves a trail instead of a
scrolled-away traceback. It's best-effort: if the log directory can't be
created it degrades quietly rather than stopping NARA from starting.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Config

_CONFIGURED = False


def setup_logging(cfg: Config, *, force: bool = False) -> logging.Logger:
    """Attach a rotating file handler to the ``nara`` logger. Idempotent."""
    global _CONFIGURED
    logger = logging.getLogger("nara")
    if _CONFIGURED and not force:
        return logger

    level_name = str(cfg.get("logging.level", "INFO")).upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))

    try:
        log_dir = Path(cfg.get("logging.path", "~/.nara/logs")).expanduser()
        log_dir.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            log_dir / "nara.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
    except OSError:
        # Can't write logs (read-only home, odd permissions) — don't crash NARA.
        handler = logging.NullHandler()

    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    # Replace our own handlers so repeated calls don't stack duplicates.
    for existing in list(logger.handlers):
        logger.removeHandler(existing)
    logger.addHandler(handler)
    logger.propagate = False
    _CONFIGURED = True
    return logger
