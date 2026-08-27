"""NARA's persona and prompt assembly (Phase 2)."""
from __future__ import annotations

from .config import Config

_SCAFFOLD = """You are {name}, a JARVIS-style personal AI assistant.

{style}

How you operate:
- Be concise and direct — no filler, no preamble, no restating the question.
- Ground answers in the notes from memory when they're relevant. If the notes
  don't cover it, say so rather than inventing specifics.
- You run in a terminal, so keep replies short and skimmable.
- For a coding task in one of the user's projects, you can run it for real with
  Claude Code: tell them to use `nara dev <project> "<task>"` (or /dev in chat).
"""


def build_system_prompt(cfg: Config) -> str:
    name = cfg.get("persona.name", "NARA")
    style = (cfg.get("persona.style") or "").strip()
    return _SCAFFOLD.format(name=name, style=style).strip()


def format_memory(results) -> str:
    """Render retrieved note chunks as a compact context block (or "")."""
    if not results:
        return ""
    lines = ["Relevant notes from your vault:"]
    for r in results:
        snippet = " ".join(r.text.split())[:300]
        location = getattr(r, "location", "") or getattr(r, "title", "")
        lines.append(f"- ({location}) {snippet}")
    return "\n".join(lines)
