"""Configuration loading for NARA (Phase 0).

Loads ``config/nara.yaml`` and the ``.env`` file, expands ``~`` and environment
variables in path-like values, and exposes the result through a small ``Config``
helper that supports dotted-key access::

    from core.config import load_config

    cfg = load_config()
    cfg.get("models.cloud_model")   # -> "claude-sonnet-5"
    cfg.vault_path                  # -> Path to the Obsidian vault
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Repo root = the directory that contains this ``core/`` package.
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "nara.yaml"

# Dotted keys whose string values are filesystem paths and should be expanded.
_PATH_KEYS = (
    "vault.path",
    "memory.index_path",
    "logging.path",
)


def _expand(value: str) -> str:
    """Expand ``~`` and ``$VARS`` in a string path."""
    return os.path.expanduser(os.path.expandvars(value))


def _get(data: dict[str, Any], dotted: str, default: Any = None) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _set(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


class Config:
    """Thin, read-friendly wrapper around the parsed YAML config."""

    def __init__(self, data: dict[str, Any], source: Path):
        self.data = data
        self.source = source

    def get(self, dotted: str, default: Any = None) -> Any:
        """Fetch a value by dotted key, e.g. ``cfg.get("models.cloud_model")``."""
        return _get(self.data, dotted, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    # ── Convenience accessors ────────────────────────────────────────────────
    @property
    def vault_path(self) -> Path:
        raw = self.get("vault.path")
        if not raw:
            raise KeyError("vault.path is not set in the config")
        return Path(raw)

    @property
    def index_path(self) -> Path:
        return Path(
            self.get("memory.index_path", str(REPO_ROOT / ".nara" / "index.lancedb"))
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Config(source={self.source})"


def load_config(config_path: str | os.PathLike[str] | None = None) -> Config:
    """Load NARA's configuration.

    Reads ``.env`` (for API keys) and ``config/nara.yaml``. Path-like values are
    expanded. The config file may be overridden with the ``NARA_CONFIG`` env var
    or the ``config_path`` argument.

    Raises:
        FileNotFoundError: if the config file cannot be found.
        ValueError: if the config file is not a YAML mapping.
    """
    # Load .env from the repo root if present (a no-op when it's absent).
    load_dotenv(REPO_ROOT / ".env")

    path = Path(config_path or os.environ.get("NARA_CONFIG") or DEFAULT_CONFIG_PATH)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"NARA config not found at {path}. Copy config/nara.yaml and adjust it, "
            "or set NARA_CONFIG to point at your config file."
        )

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        # A malformed config file is a value error (bad file contents), not a
        # programmer type error — hence ValueError over TypeError.
        raise ValueError(
            f"Config at {path} must be a YAML mapping, got {type(data).__name__}."
        )

    # Expand path-like values in place.
    for key in _PATH_KEYS:
        val = _get(data, key)
        if isinstance(val, str) and val:
            _set(data, key, _expand(val))

    # Expand project repo paths (dev.projects: name -> path).
    projects = _get(data, "dev.projects")
    if isinstance(projects, dict):
        for name, repo_path in list(projects.items()):
            if isinstance(repo_path, str):
                projects[name] = _expand(repo_path)

    return Config(data, path)
