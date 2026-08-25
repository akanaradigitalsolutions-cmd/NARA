"""Phase 0 smoke tests: config loads and the orchestrator stub runs."""
from __future__ import annotations

from core.config import load_config


def test_config_loads():
    cfg = load_config()
    assert cfg.get("persona.name")
    assert cfg.get("models.cloud_model")
    assert cfg.get("vault.path")
    assert cfg.get("cloud.backend") in {"cli", "api"}


def test_dotted_get_default():
    cfg = load_config()
    assert cfg.get("does.not.exist", "fallback") == "fallback"


def test_path_expansion():
    cfg = load_config()
    # ~ should have been expanded away during load.
    assert "~" not in str(cfg.get("vault.path"))


def test_orchestrator_prints_online(capsys):
    from core.orchestrator import main

    main()
    out = capsys.readouterr().out
    assert "online" in out.lower()
