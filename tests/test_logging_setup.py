"""Phase 8 tests: file logging setup, offline and hermetic (uses tmp paths)."""
from __future__ import annotations

import logging
from pathlib import Path

from core.config import Config
from core.logging_setup import setup_logging


def test_writes_to_rotating_file(tmp_path):
    cfg = Config({"logging": {"path": str(tmp_path / "logs"), "level": "DEBUG"}}, Path("x"))
    logger = setup_logging(cfg, force=True)
    logger.info("hello nara")
    for handler in logger.handlers:
        handler.flush()
    log_file = tmp_path / "logs" / "nara.log"
    assert log_file.exists()
    assert "hello nara" in log_file.read_text(encoding="utf-8")
    assert logger.level == logging.DEBUG


def test_survives_unwritable_path(tmp_path):
    # Parent is a regular file, so the log dir can't be created — must not raise.
    afile = tmp_path / "afile"
    afile.write_text("x", encoding="utf-8")
    cfg = Config({"logging": {"path": str(afile / "logs")}}, Path("x"))
    logger = setup_logging(cfg, force=True)
    logger.info("still works")  # swallowed by the NullHandler fallback
    assert logger.level == logging.INFO
