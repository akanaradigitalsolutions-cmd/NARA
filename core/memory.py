"""Vault memory — RAG over the Obsidian vault.

Implemented in **Phase 1 — The Brain**. This module will expose a
``MemoryManager`` with:

    search(query, k=6)      -> ranked note chunks with titles
    remember(text, tags=[]) -> write a timestamped note to NARA/Memory/
    daily_log(text)         -> append a bullet to today's note in NARA/Daily/

For now the methods raise ``NotImplementedError`` so the interface is
discoverable and the orchestrator can import against it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MemoryManager:
    """RAG over the Obsidian vault. See the module docstring (Phase 1)."""

    def search(self, query: str, k: int = 6):
        raise NotImplementedError("Phase 1: implement vault semantic search")

    def remember(self, text: str, tags: list[str] | None = None):
        raise NotImplementedError("Phase 1: implement note writing to NARA/Memory/")

    def daily_log(self, text: str):
        raise NotImplementedError("Phase 1: implement the daily-log append")
