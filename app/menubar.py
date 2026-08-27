"""NARA menu-bar app for macOS (Phase 5).

A lightweight always-there presence using rumps (pure Python — no Rust/Node).
Menu items open a Terminal running NARA's chat or voice loop, reindex the vault,
show status, or quit. rumps is macOS-only and imported lazily, so this module
loads (and its pure helpers stay testable) on any platform.

Run:  nara menubar   (or launch at login — see scripts/install_menubar.py)
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def terminal_script(command: str) -> str:
    """AppleScript that runs `command` in a new Terminal window, in the venv."""
    inner = f"cd {REPO} && source .venv/bin/activate && {command}"
    return f'tell application "Terminal" to do script "{inner}"'


def open_terminal(command: str) -> None:
    subprocess.run(["osascript", "-e", terminal_script(command)], check=False)


def build_app():
    import rumps

    class NaraApp(rumps.App):
        def __init__(self):
            super().__init__("NARA", quit_button=None)
            self.menu = ["Chat", "Talk", "Reindex vault", "Status", None, "Quit"]

        @rumps.clicked("Chat")
        def chat(self, _):
            open_terminal("nara")

        @rumps.clicked("Talk")
        def talk(self, _):
            open_terminal("nara voice")

        @rumps.clicked("Reindex vault")
        def reindex(self, _):
            open_terminal("python scripts/index_vault.py")

        @rumps.clicked("Status")
        def status(self, _):
            open_terminal("nara --status")

        @rumps.clicked("Quit")
        def quit_app(self, _):
            rumps.quit_application()

    return NaraApp()


def main() -> None:
    try:
        app = build_app()
    except ImportError as exc:  # rumps missing / not on macOS
        raise SystemExit(
            "The menu-bar app needs rumps (macOS): uv pip install -e '.[menubar]'"
        ) from exc
    app.run()


if __name__ == "__main__":
    main()
