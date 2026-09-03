"""Content skill (Phase 7): draft marketing content from your vault.

Pulls a brief from vault memory and drafts captions / listing copy / outreach,
optionally bilingual (Bahasa Indonesia + English). Saves the draft under
``NARA/Content/``. The ``engine`` and ``memory`` are injectable for testing.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

_KINDS = {
    "caption": "3 Instagram caption options, each with a few relevant hashtags",
    "listing": "spa/property listing copy: a punchy headline plus two short paragraphs",
    "outreach": "a short, warm partner-outreach message",
}


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50].strip("-") or "draft"


class ContentSkill:
    def __init__(self, vault_path, memory, engine, save_folder="NARA/Content", search_k=5):
        self.vault_path = Path(vault_path)
        self.memory = memory
        self.engine = engine
        self.save_folder = save_folder
        self.search_k = search_k

    @classmethod
    def from_config(cls, cfg, memory, engine):
        return cls(
            cfg.get("vault.path"),
            memory,
            engine,
            save_folder=cfg.get("content.save_folder", "NARA/Content"),
            search_k=cfg.get("content.search_k", 5),
        )

    def draft(self, topic: str, kind: str = "caption", bilingual: bool = False):
        try:
            notes = self.memory.search(topic, k=self.search_k)
        except Exception:
            notes = []
        brief = "\n".join(f"- {' '.join(n.text.split())[:200]}" for n in notes)
        brief = brief or "(no matching vault notes — use sensible defaults)"

        want = _KINDS.get(kind, _KINDS["caption"])
        lang = (
            "Write it in BOTH Bahasa Indonesia and English (Bahasa first, then English)."
            if bilingual
            else "Write it in English."
        )
        system = (
            "You are a sharp, concise marketing copywriter for a Bali spa, laundry and "
            "hospitality brand. Keep it on-brand, specific, and ready to post."
        )
        prompt = f"Draft {want} about: {topic}\n\n{lang}\n\nGround it in these notes:\n{brief}"
        text = self.engine.generate(system, [{"role": "user", "content": prompt}]).text
        return text, self._save(topic, kind, text)

    def _save(self, topic: str, kind: str, text: str) -> Path:
        folder = self.vault_path / self.save_folder
        folder.mkdir(parents=True, exist_ok=True)
        now = datetime.now().astimezone()
        path = folder / f"{now:%Y-%m-%d}_{kind}_{_slug(topic)}.md"
        header = f"# {kind.title()} — {topic}\n\n_Drafted {now:%Y-%m-%d %H:%M}_\n\n"
        path.write_text(header + (text or "").strip() + "\n", encoding="utf-8")
        return path
