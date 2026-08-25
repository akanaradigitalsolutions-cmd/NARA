"""(Re)build the vault vector index.

Implemented in **Phase 1 — The Brain**. Walks the Obsidian vault, chunks notes
by heading, embeds each chunk with Ollama's ``nomic-embed-text``, and upserts
vectors + metadata into LanceDB. A filesystem watcher keeps it incremental.

Usage (Phase 1+)::

    python scripts/index_vault.py [--watch]
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    print(
        "index_vault.py is a Phase 0 stub — vault indexing arrives in Phase 1.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
