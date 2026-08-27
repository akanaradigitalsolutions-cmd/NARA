"""Install/uninstall a macOS LaunchAgent so NARA's menu-bar app starts at login.

    python scripts/install_menubar.py            # write the plist + load it now
    python scripts/install_menubar.py --uninstall

The agent runs `<repo>/.venv/bin/python -m app.menubar` at login and keeps it
alive. Uses launchctl; no sudo required (per-user LaunchAgent).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LABEL = "com.nara.menubar"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def build_plist(python: str, label: str = LABEL, workdir: str | None = None) -> str:
    workdir = workdir or str(REPO)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>app.menubar</string>
    </array>
    <key>WorkingDirectory</key><string>{workdir}</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><false/>
</dict>
</plist>
"""


def install() -> int:
    python = REPO / ".venv" / "bin" / "python"
    if not python.exists():
        print(f"✗ venv python not found at {python}. Run setup_mac.sh first.", file=sys.stderr)
        return 1
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(build_plist(str(python)), encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True, check=False)
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print(f"✗ launchctl load failed: {result.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"✓ NARA menu-bar app installed and will start at login.\n  {PLIST_PATH}")
    return 0


def uninstall() -> int:
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True, check=False)
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
    print("✓ NARA menu-bar app removed from login items.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install NARA's menu-bar app at login.")
    parser.add_argument("--uninstall", action="store_true", help="remove the login item")
    args = parser.parse_args(argv)
    return uninstall() if args.uninstall else install()


if __name__ == "__main__":
    raise SystemExit(main())
