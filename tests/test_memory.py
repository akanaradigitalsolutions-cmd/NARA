"""Phase 1 tests: chunking, indexing, semantic search, remember, daily_log.

These run fully offline — no Ollama, no cloud — by injecting the deterministic
``HashEmbedder`` and pointing the index at a temp LanceDB.
"""
from __future__ import annotations

import os
import time

import pytest

from core.memory import HashEmbedder, MemoryManager, chunk_markdown


# ── Fixtures ─────────────────────────────────────────────────────────────────
def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    _write(root / "Projects" / "Relaxha.md",
           "# Relaxha pricing\n\nRelaxha spa pricing: aromatherapy massage 150k, "
           "facial treatment 200k, sauna 80k. #relaxha #pricing")
    _write(root / "Projects" / "Laundry.md",
           "# AKA Express Laundry\n\nWash and fold is 10k per kilogram. "
           "Express same-day service costs double.")
    # Should be skipped:
    _write(root / ".obsidian" / "workspace.md", "# obsidian internals\n\nignore me")
    _write(root / "NARA" / "private" / "secret.md",
           "# private diary\n\nRelaxha secret sauce recipe, never leave the machine")
    return root


@pytest.fixture
def manager(vault, tmp_path):
    return MemoryManager(
        vault_path=vault,
        index_path=tmp_path / "index.lancedb",
        embedder=HashEmbedder(dim=256),
    )


# ── Chunking ─────────────────────────────────────────────────────────────────
def test_chunk_markdown_by_heading():
    text = "# One\n\nAlpha body.\n\n## Two\n\nBeta body."
    chunks = chunk_markdown(text)
    headings = {c.heading for c in chunks}
    assert "One" in headings and "Two" in headings


def test_chunk_markdown_splits_long_sections():
    long_body = "# Big\n\n" + ("word " * 4000)
    chunks = chunk_markdown(long_body, chunk_size=200, overlap=20)
    assert len(chunks) > 1
    assert all(c.heading == "Big" for c in chunks)


# ── Indexing + search ────────────────────────────────────────────────────────
def test_index_and_search(manager):
    stats = manager.reindex()
    assert stats.files_indexed == 2  # Relaxha + Laundry; private/.obsidian skipped
    assert manager.store.count() >= 2

    results = manager.search("Relaxha spa massage pricing", k=3)
    assert results, "expected at least one search result"
    assert results[0].path == "Projects/Relaxha.md"
    assert "Relaxha" in results[0].title


def test_private_and_obsidian_skipped(manager, vault):
    manager.reindex()
    # The private note mentions "Relaxha" but must never be indexed/returned.
    for r in manager.search("secret sauce recipe diary", k=10):
        assert "private" not in r.path
        assert ".obsidian" not in r.path


def test_reindex_is_idempotent(manager):
    manager.reindex()
    second = manager.reindex()
    assert second.files_indexed == 0
    assert second.files_skipped == 2


def test_reindex_picks_up_changes(manager, vault):
    manager.reindex()
    note = vault / "Projects" / "Laundry.md"
    note.write_text("# Laundry\n\nNew pricing: 12k per kilo.", encoding="utf-8")
    os.utime(note, (time.time() + 10, time.time() + 10))  # force a newer mtime
    stats = manager.reindex()
    assert stats.files_indexed == 1


def test_delete_is_reflected(manager, vault):
    manager.reindex()
    (vault / "Projects" / "Laundry.md").unlink()
    stats = manager.reindex()
    assert stats.files_removed == 1
    for r in manager.search("wash and fold laundry", k=10):
        assert r.path != "Projects/Laundry.md"


# ── Writing ──────────────────────────────────────────────────────────────────
def test_remember_writes_and_indexes(manager):
    manager.reindex()
    path = manager.remember("Umalas villa cleaning fee is 500k per stay.", tags=["relaxha", "ops"])
    assert path.exists()
    assert path.parent.name == "Memory"
    assert "Umalas" in path.read_text(encoding="utf-8")
    # Immediately searchable (remember indexes inline).
    results = manager.search("Umalas villa cleaning fee", k=5)
    assert any("Umalas" in r.text for r in results)


def test_daily_log_appends(manager):
    p1 = manager.daily_log("Called the laundry supplier.")
    p2 = manager.daily_log("Drafted Relaxha promo.")
    assert p1 == p2  # same day → same file
    bullets = [ln for ln in p1.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")]
    assert len(bullets) == 2


# ── Error handling ───────────────────────────────────────────────────────────
def test_missing_vault(tmp_path):
    mm = MemoryManager(
        vault_path=tmp_path / "does-not-exist",
        index_path=tmp_path / "idx.lancedb",
        embedder=HashEmbedder(dim=64),
    )
    assert mm.search("anything") == []          # empty index → no results, no error
    with pytest.raises(FileNotFoundError):
        mm.reindex()
    with pytest.raises(FileNotFoundError):
        mm.remember("nope")
