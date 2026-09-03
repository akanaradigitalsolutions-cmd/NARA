"""Phase 8 tests: the `nara doctor` health check, fully offline.

Every side-effecting probe (which, env, Ollama models, index count, free disk,
home dir, Python version) is faked through ``Probes``, so no real subprocess,
network, or model is touched.
"""
from __future__ import annotations

from pathlib import Path

from core.config import Config
from core.doctor import Check, Probes, _has_model, exit_code, run_checks, worst


def make_probes(**over) -> Probes:
    base = {
        "which": lambda name: f"/usr/bin/{name}",
        "env": {},
        "ollama_models": lambda: ["qwen3:4b", "nomic-embed-text:latest"],
        "index_count": lambda cfg: 5,
        "disk_free_gb": lambda path: 50.0,
        "home": Path("/fake/home"),
        "python_version": (3, 12),
    }
    base.update(over)
    return Probes(**base)


def _cfg(tmp_path, *, backend="cli", vault=True, source="nara.yaml") -> Config:
    vault_path = tmp_path / "vault"
    if vault:
        vault_path.mkdir(exist_ok=True)
    data = {
        "cloud": {"backend": backend},
        "vault": {"path": str(vault_path)},
        "agent": {"local_model": "qwen3:4b"},
        "models": {"embedding_model": "nomic-embed-text"},
        "logging": {"path": str(tmp_path / "logs")},
    }
    return Config(data, Path(source))


def by_name(checks: list[Check], name: str) -> Check:
    return next(c for c in checks if c.name == name)


def test_all_green(tmp_path):
    agents = tmp_path / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "com.nara.service.plist").write_text("x", encoding="utf-8")
    checks = run_checks(_cfg(tmp_path), make_probes(home=tmp_path))
    assert worst(checks) == "ok"
    assert exit_code(checks) == 0


def test_missing_vault_fails(tmp_path):
    checks = run_checks(_cfg(tmp_path, vault=False), make_probes())
    assert by_name(checks, "Vault").status == "fail"
    assert exit_code(checks) == 1


def test_cloud_cli_missing_claude_fails(tmp_path):
    probes = make_probes(which=lambda name: None)
    assert by_name(run_checks(_cfg(tmp_path), probes), "Cloud · cli").status == "fail"


def test_cloud_cli_warns_when_api_key_present(tmp_path):
    probes = make_probes(env={"ANTHROPIC_API_KEY": "sk-xxx"})
    assert by_name(run_checks(_cfg(tmp_path), probes), "Cloud · cli").status == "warn"


def test_cloud_api_backend_needs_key(tmp_path):
    api_cfg = _cfg(tmp_path, backend="api")
    no_key = run_checks(api_cfg, make_probes(env={}))
    assert by_name(no_key, "Cloud · api").status == "fail"
    with_key = run_checks(api_cfg, make_probes(env={"ANTHROPIC_API_KEY": "x"}))
    assert by_name(with_key, "Cloud · api").status == "ok"


def test_ollama_missing_model_warns(tmp_path):
    probes = make_probes(ollama_models=lambda: ["qwen3:4b"])  # embedding model absent
    check = by_name(run_checks(_cfg(tmp_path), probes), "Ollama")
    assert check.status == "warn"
    assert "nomic-embed-text" in check.detail


def test_ollama_unreachable_warns(tmp_path):
    probes = make_probes(ollama_models=lambda: [])
    assert by_name(run_checks(_cfg(tmp_path), probes), "Ollama").status == "warn"


def test_index_states(tmp_path):
    empty = run_checks(_cfg(tmp_path), make_probes(index_count=lambda cfg: 0))
    assert by_name(empty, "Vault index").status == "warn"
    unavailable = run_checks(_cfg(tmp_path), make_probes(index_count=lambda cfg: -1))
    assert by_name(unavailable, "Vault index").status == "warn"
    built = run_checks(_cfg(tmp_path), make_probes(index_count=lambda cfg: 12))
    assert by_name(built, "Vault index").status == "ok"


def test_example_config_warns(tmp_path):
    checks = run_checks(_cfg(tmp_path, source="nara.example.yaml"), make_probes())
    assert by_name(checks, "Config").status == "warn"


def test_low_disk_warns(tmp_path):
    probes = make_probes(disk_free_gb=lambda path: 1.0)
    assert by_name(run_checks(_cfg(tmp_path), probes), "Disk").status == "warn"


def test_old_python_warns(tmp_path):
    probes = make_probes(python_version=(3, 11))
    assert by_name(run_checks(_cfg(tmp_path), probes), "Python").status == "warn"


def test_has_model_matching():
    assert _has_model(["qwen3:4b"], "qwen3:4b")
    assert _has_model(["nomic-embed-text:latest"], "nomic-embed-text")
    assert not _has_model(["qwen3:8b"], "qwen3:4b")
    assert not _has_model([], "qwen3:4b")


def test_exit_code_and_worst_ordering():
    checks = [Check("a", "ok"), Check("b", "warn"), Check("c", "ok")]
    assert worst(checks) == "warn"
    assert exit_code(checks) == 0
    checks.append(Check("d", "fail"))
    assert worst(checks) == "fail"
    assert exit_code(checks) == 1
