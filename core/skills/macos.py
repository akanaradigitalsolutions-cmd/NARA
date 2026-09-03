"""macOS control skill (Phase 7).

Open/activate apps, run named Shortcuts, and set Focus via ``osascript`` and the
``shortcuts`` CLI. macOS-only at runtime; the command builders are pure Python
and testable anywhere via an injectable runner.
"""
from __future__ import annotations

import subprocess


def _osascript_runner(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:300] or f"exit {proc.returncode}")
    return (proc.stdout or "").strip()


class MacControl:
    """Thin wrapper over osascript / the `shortcuts` CLI."""

    def __init__(self, runner=None):
        self._runner = runner or _osascript_runner

    def run_applescript(self, script: str) -> str:
        return self._runner(["osascript", "-e", script])

    def open_app(self, name: str) -> str:
        self.run_applescript(f'tell application "{name}" to activate')
        return f"Opened {name}."

    def run_shortcut(self, name: str) -> str:
        self._runner(["shortcuts", "run", name])
        return f"Ran Shortcut “{name}”."

    def set_focus(self, mode: str) -> str:
        # macOS Focus modes are best toggled by a user Shortcut named for the mode.
        self._runner(["shortcuts", "run", mode])
        return f"Set Focus via Shortcut “{mode}”."

    def list_shortcuts(self) -> list[str]:
        out = self._runner(["shortcuts", "list"])
        return [line.strip() for line in out.splitlines() if line.strip()]
