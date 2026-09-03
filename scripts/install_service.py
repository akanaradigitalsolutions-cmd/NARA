"""Install/uninstall a macOS LaunchAgent so NARA's core service runs at login.

    python scripts/install_service.py            # write the plist + start it now
    python scripts/install_service.py --uninstall

The agent runs `<repo>/.venv/bin/nara serve` — NARA's local HTTP core (Phase 5) —
at login and, with KeepAlive, restarts it automatically if it ever crashes. This
is what makes NARA restart-safe and always reachable. Output is captured under
`~/.nara/logs/`. Uses launchctl; no sudo required (per-user LaunchAgent).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LABEL = "com.nara.service"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / ".nara" / "logs"


def build_plist(nara_bin: str, label: str = LABEL, workdir: str | None = None) -> str:
    workdir = workdir or str(REPO)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{nara_bin}</string>
        <string>serve</string>
    </array>
    <key>WorkingDirectory</key><string>{workdir}</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>{LOG_DIR / "service.out.log"}</string>
    <key>StandardErrorPath</key><string>{LOG_DIR / "service.err.log"}</string>
</dict>
</plist>
"""


def install() -> int:
    nara_bin = REPO / ".venv" / "bin" / "nara"
    if not nara_bin.exists():
        print(f"✗ nara not found at {nara_bin}. Run setup_mac.sh first.", file=sys.stderr)
        return 1
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(build_plist(str(nara_bin)), encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True, check=False)
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print(f"✗ launchctl load failed: {result.stderr.strip()}", file=sys.stderr)
        return 1
    print(
        f"✓ NARA service installed — it starts at login and restarts if it crashes.\n"
        f"  {PLIST_PATH}\n  Reachable at http://127.0.0.1:8765 (see `nara doctor`)."
    )
    return 0


def uninstall() -> int:
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True, check=False)
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
    print("✓ NARA service removed from login items.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install NARA's always-on service at login.")
    parser.add_argument("--uninstall", action="store_true", help="remove the login item")
    args = parser.parse_args(argv)
    return uninstall() if args.uninstall else install()


if __name__ == "__main__":
    raise SystemExit(main())
