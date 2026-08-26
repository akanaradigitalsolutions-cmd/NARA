"""Point NARA at your Obsidian vault — safely, without hand-editing YAML.

Usage:
    python scripts/set_vault.py --list                # list Obsidian vaults on this Mac
    python scripts/set_vault.py "~/Documents/MyVault"  # set vault.path to that folder
    python scripts/set_vault.py --create ~/NARA-Vault  # make a new folder and use it

Only the `vault.path` line in config/nara.yaml is touched; comments and every
other setting are preserved.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CONFIG = _CONFIG_DIR / "nara.yaml"
EXAMPLE = _CONFIG_DIR / "nara.example.yaml"
OBSIDIAN_JSON = Path.home() / "Library/Application Support/obsidian/obsidian.json"


def list_vaults() -> int:
    if not OBSIDIAN_JSON.exists():
        print(
            "No Obsidian config found on this Mac.\n"
            "If you use Obsidian, open your vault once so it registers, then re-run "
            "--list.\nNo vault yet? Create one:  python scripts/set_vault.py --create "
            "~/NARA-Vault"
        )
        return 0
    data = json.loads(OBSIDIAN_JSON.read_text(encoding="utf-8"))
    vaults = [v.get("path") for v in data.get("vaults", {}).values() if v.get("path")]
    if not vaults:
        print("No vaults are registered in Obsidian yet.")
    else:
        print("Your Obsidian vaults:")
        for path in vaults:
            print(f"  {path}")
        print('\nSet one with:  python scripts/set_vault.py "<path>"')
    return 0


def set_vault(raw_path: str, create: bool) -> int:
    vault = Path(raw_path).expanduser()
    if create:
        vault.mkdir(parents=True, exist_ok=True)
    if not vault.is_dir():
        print(
            f"✗ Folder does not exist: {vault}\n"
            "  Pass the correct path, or add --create to make a new folder.",
            file=sys.stderr,
        )
        return 1

    if not CONFIG.exists() and EXAMPLE.exists():
        CONFIG.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    lines = CONFIG.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    in_vault = False
    done = False
    for line in lines:
        stripped = line.rstrip("\n")
        if not done:
            if stripped.startswith("vault:"):
                in_vault = True
            elif in_vault and stripped and not stripped[0].isspace():
                in_vault = False  # a new top-level section began
            elif in_vault and stripped.lstrip().startswith("path:"):
                indent = line[: len(line) - len(line.lstrip())]
                line = f'{indent}path: "{vault}"\n'
                done = True
        out.append(line)

    if not done:
        print("✗ Could not find vault.path in config/nara.yaml", file=sys.stderr)
        return 1
    CONFIG.write_text("".join(out), encoding="utf-8")
    print(f"✓ vault.path set to {vault}")
    print("Next:  python scripts/index_vault.py")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Point NARA at your Obsidian vault.")
    parser.add_argument("path", nargs="?", help="path to your vault folder")
    parser.add_argument("--create", action="store_true", help="create the folder if missing")
    parser.add_argument("--list", action="store_true", help="list Obsidian vaults on this Mac")
    args = parser.parse_args(argv)

    if args.list or not args.path:
        return list_vaults()
    return set_vault(args.path, args.create)


if __name__ == "__main__":
    raise SystemExit(main())
