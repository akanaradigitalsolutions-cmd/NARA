"""Phase 5 tests: menu-bar + launch-agent pure helpers (no macOS needed)."""
from __future__ import annotations

from app.menubar import terminal_script
from scripts.install_menubar import build_plist


def test_terminal_script_wraps_command():
    script = terminal_script("nara voice")
    assert "Terminal" in script
    assert "nara voice" in script
    assert "source .venv/bin/activate" in script


def test_build_plist_has_python_module_and_autostart():
    xml = build_plist("/opt/nara/.venv/bin/python", label="com.test.nara")
    assert "com.test.nara" in xml
    assert "/opt/nara/.venv/bin/python" in xml
    assert "app.menubar" in xml
    assert "<key>RunAtLoad</key>" in xml
