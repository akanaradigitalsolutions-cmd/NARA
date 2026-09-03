"""Phase 8 tests: the always-on service LaunchAgent plist builder.

Loaded by file path so it works whether or not ``scripts`` is an importable
package. Only the pure ``build_plist`` is exercised (no launchctl).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parent.parent / "scripts" / "install_service.py"
    spec = importlib.util.spec_from_file_location("install_service", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_plist_runs_nara_serve_and_keeps_alive():
    mod = _load()
    plist = mod.build_plist("/Users/me/NARA/.venv/bin/nara")
    assert "<string>serve</string>" in plist
    assert "/Users/me/NARA/.venv/bin/nara" in plist
    assert "<key>KeepAlive</key><true/>" in plist  # restart on crash
    assert "<key>RunAtLoad</key><true/>" in plist  # start at login
    assert mod.LABEL in plist


def test_plist_captures_logs():
    mod = _load()
    plist = mod.build_plist("/x/nara")
    assert "StandardOutPath" in plist and "StandardErrorPath" in plist
