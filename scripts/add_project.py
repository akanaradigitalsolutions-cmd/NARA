"""Register a project repo for `nara dev`, without hand-editing YAML.

Usage:
    python scripts/add_project.py relaxha ~/code/relaxha
    python scripts/add_project.py --list

Adds (or updates) an entry under `dev.projects` in config/nara.yaml. Comments
and every other setting are preserved. After this, run:
    nara dev relaxha "your task"
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CONFIG = _CONFIG_DIR / "nara.yaml"
EXAMPLE = _CONFIG_DIR / "nara.example.yaml"


def _ensure_config() -> None:
    if not CONFIG.exists() and EXAMPLE.exists():
        CONFIG.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")


def _dev_bounds(lines: list[str]) -> tuple[int | None, int]:
    """Return (index of `dev:` line, index just past the dev block)."""
    start = None
    for i, line in enumerate(lines):
        if line.rstrip("\n").startswith("dev:"):
            start = i
            break
    if start is None:
        return None, len(lines)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].rstrip("\n")
        if stripped and not stripped[0].isspace():
            end = i
            break
    return start, end


def list_projects() -> int:
    _ensure_config()
    lines = CONFIG.read_text(encoding="utf-8").splitlines()
    start, end = _dev_bounds(lines)
    entries = []
    if start is not None:
        in_projects = False
        for i in range(start, end):
            s = lines[i].strip()
            if s.startswith("projects:"):
                in_projects = True
                continue
            if in_projects and s and not s.startswith("#") and ":" in s:
                entries.append("  " + s)
    print("Configured projects:" if entries else "No projects configured yet.")
    for entry in entries:
        print(entry)
    print('\nAdd one with:  python scripts/add_project.py <name> <path/to/repo>')
    return 0


def add_project(name: str, raw_path: str) -> int:
    repo = Path(raw_path).expanduser()
    if not repo.is_dir():
        print(
            f"✗ Repo folder does not exist: {repo}\n"
            "  Pass the path to an existing local git repo.",
            file=sys.stderr,
        )
        return 1

    _ensure_config()
    lines = CONFIG.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = _dev_bounds(lines)
    entry_value = f'"{repo}"'

    if start is None:  # no dev section at all — append a fresh one
        lines.append(f'\ndev:\n  projects:\n    {name}: {entry_value}\n')
        CONFIG.write_text("".join(lines), encoding="utf-8")
        print(f"✓ Added project '{name}' -> {repo}")
        return 0

    proj_idx = None
    for i in range(start, end):
        if lines[i].strip().startswith("projects:"):
            proj_idx = i
            break
    if proj_idx is None:  # dev section without a projects map
        lines.insert(end, f'  projects:\n    {name}: {entry_value}\n')
        CONFIG.write_text("".join(lines), encoding="utf-8")
        print(f"✓ Added project '{name}' -> {repo}")
        return 0

    # Replace an existing entry with the same name, if present.
    entry_re = re.compile(rf"^(\s+){re.escape(name)}\s*:")
    for i in range(proj_idx + 1, end):
        m = entry_re.match(lines[i])
        if m:
            lines[i] = f"{m.group(1)}{name}: {entry_value}\n"
            CONFIG.write_text("".join(lines), encoding="utf-8")
            print(f"✓ Updated project '{name}' -> {repo}")
            return 0

    # Otherwise insert a new entry, matching the indent of existing entries.
    indent = "    "
    for i in range(proj_idx + 1, end):
        body = lines[i].strip()
        if body and not body.startswith("#"):
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            break
    lines.insert(proj_idx + 1, f"{indent}{name}: {entry_value}\n")
    CONFIG.write_text("".join(lines), encoding="utf-8")
    print(f"✓ Added project '{name}' -> {repo}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register a repo for `nara dev`.")
    parser.add_argument("name", nargs="?", help="short project name, e.g. relaxha")
    parser.add_argument("path", nargs="?", help="path to the local git repo")
    parser.add_argument("--list", action="store_true", help="list configured projects")
    args = parser.parse_args(argv)

    if args.list or not args.name or not args.path:
        return list_projects()
    return add_project(args.name, args.path)


if __name__ == "__main__":
    raise SystemExit(main())
