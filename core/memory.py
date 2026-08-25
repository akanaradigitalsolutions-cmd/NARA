"""Vault memory — RAG over the Obsidian vault (Phase 1 — The Brain).

``MemoryManager`` is NARA's long-term memory. It:

- ``search(query, k)``      — semantic recall over the indexed vault
- ``remember(text, tags)``  — write a timestamped note into ``NARA/Memory/``
- ``daily_log(text)``       — append a bullet to today's note in ``NARA/Daily/``
- ``reindex()`` / ``index_file()`` / ``remove_file()`` — (re)build the index

The vector index is LanceDB; embeddings come from Ollama's ``nomic-embed-text``
by default. Both are behind small abstractions so the pipeline is testable
offline (see ``HashEmbedder``). LanceDB is imported lazily so the base install
(without the ``[memory]`` extra) can still import this module.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from .config import Config, load_config

logger = logging.getLogger("nara.memory")

# Directories/files never indexed regardless of config.
_ALWAYS_SKIP = {".obsidian", ".trash", ".git"}
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _field(resp, name):
    """Read ``name`` from a dict or an object (the ollama client returns either)."""
    return resp.get(name) if isinstance(resp, dict) else getattr(resp, name, None)


def _table_names(db) -> list[str]:
    """List table names across LanceDB versions (list_tables vs table_names)."""
    lister = getattr(db, "list_tables", None)
    if lister is None:
        return list(db.table_names())
    resp = lister()
    return list(getattr(resp, "tables", resp))


# ─────────────────────────────────────────────────────────────────────────────
# Embedders
# ─────────────────────────────────────────────────────────────────────────────
@runtime_checkable
class Embedder(Protocol):
    """Turns text into vectors. ``embed`` must return one vector per input."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    """Embeds via a local Ollama model (default: ``nomic-embed-text``)."""

    def __init__(self, model: str = "nomic-embed-text", host: str | None = None):
        self.model = model
        self.host = host
        self.dim: int | None = None
        self._client = None

    def _c(self):
        import ollama

        if self.host:
            if self._client is None:
                self._client = ollama.Client(host=self.host)
            return self._client
        return ollama

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._c()
        vecs: list | None = None
        try:  # newer batch API: ollama.embed(model=, input=[...])
            resp = client.embed(model=self.model, input=list(texts))
            vecs = _field(resp, "embeddings")
        except (AttributeError, TypeError):
            vecs = None
        if not vecs:  # fall back to the older per-item API
            vecs = []
            for text in texts:
                vecs.append(_field(client.embeddings(model=self.model, prompt=text), "embedding"))
        out = [[float(x) for x in v] for v in vecs]
        if out:
            self.dim = len(out[0])
        return out


class HashEmbedder:
    """Deterministic, dependency-free embedder for tests and offline use.

    A hashing bag-of-words vectorizer: texts sharing words land near each other,
    so semantic-ish search is meaningful without a running Ollama.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            for tok in re.findall(r"\w+", text.lower()):
                h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:8], "little")
                vec[h % self.dim] += 1.0
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec /= norm
            out.append(vec.tolist())
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Chunking + light metadata extraction
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Chunk:
    heading: str
    text: str


def _split_text(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    """Sliding-window split that prefers to break on paragraph/line boundaries."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= target_chars:
        return [text]
    chunks: list[str] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + target_chars, n)
        if end < n:
            for sep in ("\n\n", "\n", ". ", " "):
                idx = text.rfind(sep, start + target_chars // 2, end)
                if idx != -1:
                    end = idx + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap_chars, start + 1)
    return chunks


def chunk_markdown(text: str, chunk_size: int = 500, overlap: int = 50) -> list[Chunk]:
    """Chunk markdown by heading, then sub-split long sections.

    ``chunk_size`` / ``overlap`` are in approximate tokens (~4 chars/token).
    """
    target_chars = max(200, chunk_size * 4)
    overlap_chars = max(0, overlap * 4)

    sections: list[tuple[str, list[str]]] = []
    heading, buf = "", []
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if buf:
                sections.append((heading, buf))
                buf = []
            heading = m.group(2).strip()
        else:
            buf.append(line)
    if buf:
        sections.append((heading, buf))

    chunks: list[Chunk] = []
    for head, lines in sections:
        body = "\n".join(lines)
        for piece in _split_text(body, target_chars, overlap_chars):
            chunks.append(Chunk(heading=head, text=piece))
    return chunks


def _note_title(text: str, path: Path) -> str:
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            return m.group(2).strip()
    return path.stem


def _extract_tags(text: str) -> list[str]:
    tags: set[str] = set()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                if line.strip().lower().startswith("tags:"):
                    val = line.split(":", 1)[1].strip().strip("[]")
                    for tok in re.split(r"[,\s]+", val):
                        tok = tok.strip().strip("\"'")
                        if tok:
                            tags.add(tok)
    for tok in re.findall(r"(?:^|\s)#([A-Za-z0-9_\-/]+)", text):
        tags.add(tok)
    return sorted(tags)


# ─────────────────────────────────────────────────────────────────────────────
# LanceDB store (imported lazily)
# ─────────────────────────────────────────────────────────────────────────────
class VaultStore:
    """Thin wrapper over a LanceDB table of note chunks."""

    def __init__(self, uri: str | Path, table: str = "chunks"):
        self.uri = str(uri)
        self.table_name = table
        self._db = None

    def _connect(self):
        import lancedb

        if self._db is None:
            Path(self.uri).parent.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self.uri)
        return self._db

    def _table(self, create_with: list[dict] | None = None):
        db = self._connect()
        if self.table_name in _table_names(db):
            return db.open_table(self.table_name)
        if create_with:
            return db.create_table(self.table_name, data=create_with)
        return None

    def add(self, records: list[dict]) -> None:
        if not records:
            return
        tbl = self._table()
        if tbl is None:
            self._table(create_with=records)
        else:
            tbl.add(records)

    def delete_path(self, rel_path: str) -> None:
        tbl = self._table()
        if tbl is not None:
            tbl.delete(f"path = '{rel_path.replace(chr(39), chr(39) * 2)}'")

    def upsert_path(self, rel_path: str, records: list[dict]) -> None:
        self.delete_path(rel_path)
        self.add(records)

    def count(self) -> int:
        tbl = self._table()
        return int(tbl.count_rows()) if tbl is not None else 0

    def search(self, vector: list[float], k: int) -> list[dict]:
        tbl = self._table()
        if tbl is None:
            return []
        return tbl.search(vector).limit(k).to_list()

    def drop(self) -> None:
        db = self._connect()
        if self.table_name in _table_names(db):
            db.drop_table(self.table_name)


# ─────────────────────────────────────────────────────────────────────────────
# Results + stats
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SearchResult:
    title: str
    heading: str
    path: str
    text: str
    distance: float

    @property
    def location(self) -> str:
        return f"{self.title} › {self.heading}" if self.heading else self.title


@dataclass
class IndexStats:
    files_indexed: int = 0
    files_skipped: int = 0
    files_removed: int = 0
    chunks_written: int = 0

    def __str__(self) -> str:
        return (
            f"indexed {self.files_indexed} file(s) "
            f"({self.chunks_written} chunk(s)), "
            f"skipped {self.files_skipped}, removed {self.files_removed}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# MemoryManager
# ─────────────────────────────────────────────────────────────────────────────
class MemoryManager:
    """NARA's long-term memory over the Obsidian vault."""

    def __init__(
        self,
        vault_path: str | Path,
        index_path: str | Path,
        embedder: Embedder,
        *,
        memory_folder: str = "NARA/Memory",
        daily_folder: str = "NARA/Daily",
        private_folder: str = "NARA/private",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        search_k: int = 6,
    ):
        self.vault_path = Path(vault_path)
        self.embedder = embedder
        self.store = VaultStore(index_path)
        self.memory_folder = memory_folder
        self.daily_folder = daily_folder
        self.private_folder = private_folder
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.search_k = search_k
        self._manifest_path = Path(str(index_path)).with_suffix(".manifest.json")

    @classmethod
    def from_config(
        cls, cfg: Config | None = None, embedder: Embedder | None = None
    ) -> MemoryManager:
        cfg = cfg or load_config()
        return cls(
            vault_path=cfg.get("vault.path"),
            index_path=cfg.get("memory.index_path"),
            embedder=embedder
            or OllamaEmbedder(cfg.get("models.embedding_model", "nomic-embed-text")),
            memory_folder=cfg.get("vault.memory_folder", "NARA/Memory"),
            daily_folder=cfg.get("vault.daily_folder", "NARA/Daily"),
            private_folder=cfg.get("vault.private_folder", "NARA/private"),
            chunk_size=cfg.get("memory.chunk_size", 500),
            chunk_overlap=cfg.get("memory.chunk_overlap", 50),
            search_k=cfg.get("memory.search_k", 6),
        )

    # ── Indexing ─────────────────────────────────────────────────────────────
    def is_indexable(self, path: Path) -> bool:
        """True if ``path`` is a vault note that should be indexed.

        Skips non-Markdown, hidden/.obsidian/.trash/.git paths, and anything
        under the configured private folder.
        """
        path = Path(path)
        if path.suffix != ".md":
            return False
        try:
            parts = path.resolve().relative_to(self.vault_path.resolve()).parts
        except ValueError:
            return False
        if any(p in _ALWAYS_SKIP or p.startswith(".") for p in parts):
            return False
        private = (self.vault_path / self.private_folder).resolve()
        return not str(path.resolve()).startswith(str(private))

    def iter_markdown_files(self) -> Iterator[Path]:
        if not self.vault_path.is_dir():
            return
        for path in self.vault_path.rglob("*.md"):
            if self.is_indexable(path):
                yield path

    def _rel(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.vault_path.resolve()))

    def _records_for(self, path: Path) -> tuple[str, list[dict]]:
        rel = self._rel(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        title = _note_title(text, path)
        tags = " ".join(_extract_tags(text))
        mtime = path.stat().st_mtime
        chunks = chunk_markdown(text, self.chunk_size, self.chunk_overlap)
        if not chunks:
            return rel, []
        vectors = self.embedder.embed([c.text for c in chunks])
        records = [
            {
                "id": f"{rel}::{i}",
                "path": rel,
                "title": title,
                "heading": c.heading,
                "text": c.text,
                "tags": tags,
                "mtime": float(mtime),
                "vector": vec,
            }
            for i, (c, vec) in enumerate(zip(chunks, vectors, strict=True))
        ]
        return rel, records

    def index_file(self, path: Path) -> int:
        """(Re)index a single note. Returns the number of chunks written."""
        rel, records = self._records_for(path)
        self.store.upsert_path(rel, records)
        manifest = self._load_manifest()
        manifest[rel] = path.stat().st_mtime
        self._save_manifest(manifest)
        return len(records)

    def remove_file(self, path: Path) -> None:
        rel = self._rel(path)
        self.store.delete_path(rel)
        manifest = self._load_manifest()
        if manifest.pop(rel, None) is not None:
            self._save_manifest(manifest)

    def reindex(self, *, rebuild: bool = False) -> IndexStats:
        """Walk the vault and bring the index up to date.

        Idempotent: unchanged files (by mtime) are skipped. Files removed from
        disk are dropped from the index.
        """
        if not self.vault_path.is_dir():
            raise FileNotFoundError(
                f"Vault path does not exist: {self.vault_path}. Set vault.path in config."
            )
        stats = IndexStats()
        if rebuild:
            self.store.drop()
            self._save_manifest({})
        elif self.store.count() == 0:
            # Store was wiped or never built — ignore any stale manifest.
            self._save_manifest({})

        manifest = self._load_manifest()
        seen: set[str] = set()
        for path in self.iter_markdown_files():
            rel = self._rel(path)
            seen.add(rel)
            mtime = path.stat().st_mtime
            if not rebuild and abs(manifest.get(rel, -1.0) - mtime) < 1e-6:
                stats.files_skipped += 1
                continue
            stats.chunks_written += self.index_file(path)
            stats.files_indexed += 1

        # Drop files that disappeared from disk.
        for rel in [r for r in manifest if r not in seen]:
            self.store.delete_path(rel)
            stats.files_removed += 1
        if stats.files_removed:
            manifest = {r: m for r, m in self._load_manifest().items() if r in seen}
            self._save_manifest(manifest)
        return stats

    def _load_manifest(self) -> dict[str, float]:
        try:
            return json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_manifest(self, manifest: dict[str, float]) -> None:
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    # ── Recall ───────────────────────────────────────────────────────────────
    def search(self, query: str, k: int | None = None) -> list[SearchResult]:
        """Return the notes most relevant to ``query`` (empty list if no index)."""
        k = k or self.search_k
        if self.store.count() == 0:
            return []
        vector = self.embedder.embed([query])[0]
        rows = self.store.search(vector, k)
        return [
            SearchResult(
                title=r.get("title", ""),
                heading=r.get("heading", ""),
                path=r.get("path", ""),
                text=r.get("text", ""),
                distance=float(r.get("_distance", 0.0)),
            )
            for r in rows
        ]

    # ── Writing ──────────────────────────────────────────────────────────────
    def _ensure_vault(self) -> None:
        if not self.vault_path.is_dir():
            raise FileNotFoundError(
                f"Vault path does not exist: {self.vault_path}. Set vault.path in config."
            )

    def remember(self, text: str, tags: Iterable[str] = ()) -> Path:
        """Write a timestamped fact into ``NARA/Memory/`` and index it."""
        self._ensure_vault()
        folder = self.vault_path / self.memory_folder
        folder.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        taglist = list(tags)
        path = folder / f"{now:%Y-%m-%d_%H%M%S}.md"
        frontmatter = (
            f"---\ncreated: {now:%Y-%m-%d %H:%M:%S}\n"
            f"tags: [{', '.join(taglist)}]\n---\n\n"
        )
        path.write_text(frontmatter + text.strip() + "\n", encoding="utf-8")
        try:  # best-effort immediate indexing so it's searchable right away
            self.index_file(path)
        except Exception:  # indexing must never lose the written note
            logger.debug("inline indexing failed for %s", path, exc_info=True)
        return path

    def daily_log(self, text: str) -> Path:
        """Append a timestamped bullet to today's note in ``NARA/Daily/``."""
        self._ensure_vault()
        folder = self.vault_path / self.daily_folder
        folder.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        path = folder / f"{now:%Y-%m-%d}.md"
        if not path.exists():
            path.write_text(f"# {now:%Y-%m-%d}\n\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"- {now:%H:%M} {text.strip()}\n")
        return path


# ─────────────────────────────────────────────────────────────────────────────
# CLI: python -m core.memory search "..."  |  remember "..."  |  daily "..."
# ─────────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    import argparse

    from rich.console import Console

    parser = argparse.ArgumentParser(
        prog="nara-memory", description="Query/write NARA's vault memory."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_search = sub.add_parser("search", help="semantic search over the vault")
    p_search.add_argument("query")
    p_search.add_argument("-k", type=int, default=None)
    p_remember = sub.add_parser("remember", help="write a fact into NARA/Memory/")
    p_remember.add_argument("text")
    p_remember.add_argument("--tags", default="")
    p_daily = sub.add_parser("daily", help="append a bullet to today's daily note")
    p_daily.add_argument("text")
    args = parser.parse_args(argv)

    console = Console()
    mm = MemoryManager.from_config()

    if args.cmd == "search":
        results = mm.search(args.query, k=args.k)
        if not results:
            console.print("[yellow]No results (is the index built? run scripts/index_vault.py)[/]")
            return 0
        for r in results:
            console.print(f"[bold cyan]{r.location}[/] [dim]({r.path}, d={r.distance:.3f})[/]")
            console.print(f"  {r.text[:200].strip()}\n")
    elif args.cmd == "remember":
        tags = [t for t in re.split(r"[,\s]+", args.tags) if t]
        path = mm.remember(args.text, tags)
        console.print(f"[green]Remembered[/] → {path}")
    elif args.cmd == "daily":
        path = mm.daily_log(args.text)
        console.print(f"[green]Logged[/] → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
