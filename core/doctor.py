"""Health check for NARA (Phase 8 — Hardening).

``run_checks`` inspects the live setup — Python, config, vault, cloud auth,
Ollama models, the vault index, disk space, logs, and login auto-start — and
returns a list of ``Check`` results with plain-language hints for anything that
needs attention. It powers ``nara doctor``.

All the side-effecting probes (``shutil.which``, the environment, the Ollama
model list, the index row count, free disk) are bundled in ``Probes`` so the
whole thing is testable offline with fakes.
"""
from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config

# Order matters: worse beats better when summarising.
_RANK = {"ok": 0, "warn": 1, "fail": 2}


@dataclass
class Check:
    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str = ""
    hint: str = ""


# ── Default probes (real I/O) ────────────────────────────────────────────────
def _ollama_models() -> list[str]:
    """Names of locally available Ollama models ([] if Ollama is unreachable)."""
    try:
        import ollama

        resp = ollama.list()
    except Exception:
        return []
    models = resp.get("models") if isinstance(resp, dict) else getattr(resp, "models", None)
    names: list[str] = []
    for m in models or []:
        if isinstance(m, dict):
            name = m.get("model") or m.get("name")
        else:
            name = getattr(m, "model", None) or getattr(m, "name", None)
        if name:
            names.append(str(name))
    return names


def _index_count(cfg: Config) -> int:
    """Chunks in the vault index; 0 if empty, -1 if it can't be read."""
    try:
        from .memory import MemoryManager

        return MemoryManager.from_config(cfg).store.count()
    except Exception:
        return -1


def _disk_free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


@dataclass
class Probes:
    which: Callable[[str], str | None] = shutil.which
    env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    ollama_models: Callable[[], list[str]] | None = None
    index_count: Callable[[Config], int] | None = None
    disk_free_gb: Callable[[Path], float] | None = None
    home: Path = field(default_factory=Path.home)
    python_version: tuple[int, int] = field(default_factory=lambda: sys.version_info[:2])

    def __post_init__(self) -> None:
        self.ollama_models = self.ollama_models or _ollama_models
        self.index_count = self.index_count or _index_count
        self.disk_free_gb = self.disk_free_gb or _disk_free_gb


# ── Individual checks ────────────────────────────────────────────────────────
def _check_python(p: Probes) -> Check:
    major, minor = p.python_version
    ok = (major, minor) >= (3, 12)
    return Check(
        "Python",
        "ok" if ok else "warn",
        f"{major}.{minor}",
        "" if ok else "NARA targets Python 3.12+.",
    )


def _check_config(cfg: Config) -> Check:
    src = Path(cfg.source)
    if src.name == "nara.example.yaml":
        return Check(
            "Config",
            "warn",
            str(src),
            "Using the shared example. Make your own with scripts/set_vault.py so "
            "`git pull` never overwrites your settings.",
        )
    return Check("Config", "ok", str(src))


def _check_vault(cfg: Config) -> Check:
    vault = cfg.get("vault.path")
    if vault and Path(vault).is_dir():
        return Check("Vault", "ok", str(vault))
    return Check(
        "Vault",
        "fail",
        str(vault or "(unset)"),
        'Point NARA at your vault: python scripts/set_vault.py "/path/to/Vault"',
    )


def _check_cloud(cfg: Config, p: Probes) -> Check:
    backend = str(cfg.get("cloud.backend", "cli")).lower()
    has_key = bool(p.env.get("ANTHROPIC_API_KEY"))
    if backend == "api":
        if has_key:
            return Check("Cloud · api", "ok", "ANTHROPIC_API_KEY set")
        return Check(
            "Cloud · api",
            "fail",
            "no API key",
            "Set ANTHROPIC_API_KEY in .env, or switch cloud.backend to cli.",
        )
    claude = p.which("claude")
    if not claude:
        return Check(
            "Cloud · cli",
            "fail",
            "claude CLI not found",
            "npm i -g @anthropic-ai/claude-code, then run `claude login`.",
        )
    if has_key:
        return Check(
            "Cloud · cli",
            "warn",
            "claude found; ANTHROPIC_API_KEY is also set",
            "Unset ANTHROPIC_API_KEY, or Claude Code bills the API instead of your plan.",
        )
    return Check("Cloud · cli", "ok", claude)


def _has_model(models: list[str], want: str) -> bool:
    for m in models:
        if m == want or m.split(":")[0] == want or m.startswith(want + ":"):
            return True
    return False


def _check_ollama(cfg: Config, p: Probes) -> Check:
    models = p.ollama_models()
    if not models:
        return Check(
            "Ollama",
            "warn",
            "not reachable or no models",
            "Start it (brew services start ollama) and pull: "
            "ollama pull qwen3:4b nomic-embed-text",
        )
    wanted = [
        cfg.get("agent.local_model") or cfg.get("models.voice_model"),
        cfg.get("models.embedding_model"),
    ]
    missing = [w for w in wanted if w and not _has_model(models, w)]
    if missing:
        return Check(
            "Ollama",
            "warn",
            f"{len(models)} model(s); missing {', '.join(missing)}",
            "Pull it: " + " && ".join(f"ollama pull {m}" for m in missing),
        )
    return Check("Ollama", "ok", f"{len(models)} model(s) available")


def _check_index(cfg: Config, p: Probes) -> Check:
    count = p.index_count(cfg)
    if count > 0:
        return Check("Vault index", "ok", f"{count} chunk(s) indexed")
    if count == 0:
        return Check(
            "Vault index", "warn", "empty", "Build it: python scripts/index_vault.py"
        )
    return Check(
        "Vault index",
        "warn",
        "not available",
        'Install the memory extra: uv pip install -e ".[memory]"',
    )


def _check_disk(p: Probes) -> Check:
    try:
        free = p.disk_free_gb(p.home)
    except Exception:
        return Check("Disk", "warn", "couldn't read free space")
    ok = free >= 5.0
    return Check(
        "Disk",
        "ok" if ok else "warn",
        f"{free:.1f} GB free",
        "" if ok else "Low disk — local models and the index need room.",
    )


def _check_logs(cfg: Config) -> Check:
    path = Path(cfg.get("logging.path", "~/.nara/logs")).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return Check("Logs", "warn", f"{path} ({exc})", "Check the folder's permissions.")
    return Check("Logs", "ok", str(path))


def _check_autostart(p: Probes) -> Check:
    agents = p.home / "Library" / "LaunchAgents"
    installed = [
        label
        for label in ("com.nara.service", "com.nara.menubar")
        if (agents / f"{label}.plist").exists()
    ]
    if installed:
        return Check("Auto-start", "ok", ", ".join(installed))
    return Check(
        "Auto-start",
        "warn",
        "no login items",
        "Start NARA at login: python scripts/install_service.py",
    )


# ── Orchestration ────────────────────────────────────────────────────────────
def run_checks(cfg: Config, probes: Probes | None = None) -> list[Check]:
    p = probes or Probes()
    return [
        _check_python(p),
        _check_config(cfg),
        _check_vault(cfg),
        _check_cloud(cfg, p),
        _check_ollama(cfg, p),
        _check_index(cfg, p),
        _check_disk(p),
        _check_logs(cfg),
        _check_autostart(p),
    ]


def worst(checks: list[Check]) -> str:
    return max((c.status for c in checks), key=lambda s: _RANK.get(s, 0), default="ok")


def exit_code(checks: list[Check]) -> int:
    """0 if nothing failed (warnings are fine), 1 if any check failed."""
    return 1 if any(c.status == "fail" for c in checks) else 0
