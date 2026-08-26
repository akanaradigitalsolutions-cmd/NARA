"""(Re)build the vault vector index (Phase 1 — The Brain).

Walks the Obsidian vault, chunks notes by heading, embeds each chunk with
Ollama's ``nomic-embed-text``, and upserts vectors + metadata into LanceDB.
Idempotent: unchanged files (by mtime) are skipped. Optionally watches the
vault and re-indexes incrementally.

Usage:
    python scripts/index_vault.py            # incremental index
    python scripts/index_vault.py --rebuild  # wipe and rebuild from scratch
    python scripts/index_vault.py --watch     # index, then watch for changes
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running as a plain script (python scripts/index_vault.py) as well as -m.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import load_config  # noqa: E402
from core.memory import MemoryManager  # noqa: E402


def _watch(mm: MemoryManager) -> int:
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print(
            "watchdog is required for --watch. Install with: pip install -e '.[memory]'",
            file=sys.stderr,
        )
        return 1

    class _Handler(FileSystemEventHandler):
        def _reindex(self, path_str: str) -> None:
            path = Path(path_str)
            if not mm.is_indexable(path):
                return
            try:
                n = mm.index_file(path)
                print(f"  ~ {mm._rel(path)} ({n} chunk(s))")
            except FileNotFoundError:
                pass  # file vanished between event and read

        def _remove(self, path_str: str) -> None:
            path = Path(path_str)
            if path.suffix == ".md":
                mm.remove_file(path)
                print(f"  - {path.name}")

        def on_created(self, event):
            if not event.is_directory:
                self._reindex(event.src_path)

        def on_modified(self, event):
            if not event.is_directory:
                self._reindex(event.src_path)

        def on_deleted(self, event):
            if not event.is_directory:
                self._remove(event.src_path)

        def on_moved(self, event):
            if not event.is_directory:
                self._remove(event.src_path)
                self._reindex(event.dest_path)

    observer = Observer()
    observer.schedule(_Handler(), str(mm.vault_path), recursive=True)
    observer.start()
    print(f"Watching {mm.vault_path} for changes — Ctrl-C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping watcher.")
        observer.stop()
    observer.join()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="index_vault", description=__doc__.splitlines()[0])
    parser.add_argument("--rebuild", action="store_true", help="wipe the index and rebuild")
    parser.add_argument("--watch", action="store_true", help="watch the vault after indexing")
    args = parser.parse_args(argv)

    cfg = load_config()
    mm = MemoryManager.from_config(cfg)

    if not mm.vault_path.is_dir():
        print(
            f"Vault path does not exist: {mm.vault_path}\n"
            'Set it with:  python scripts/set_vault.py "/path/to/your/vault"\n'
            "  (find yours:  python scripts/set_vault.py --list"
            "  ·  make one:  python scripts/set_vault.py --create ~/NARA-Vault)",
            file=sys.stderr,
        )
        return 1

    print(f"Indexing {mm.vault_path} → {mm.store.uri}")
    stats = mm.reindex(rebuild=args.rebuild)
    print(f"Done: {stats}. Index now holds {mm.store.count()} chunk(s).")

    if args.watch:
        return _watch(mm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
