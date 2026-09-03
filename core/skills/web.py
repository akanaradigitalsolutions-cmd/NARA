"""Web skill (Phase 7): search/fetch and summarize into the vault.

Delegates the actual web work to Claude Code (which has web search + fetch), so
it runs on a Pro/Max subscription with no extra API, then saves the summary as a
note under ``NARA/Web/``. The ``researcher`` callable is injectable for testing.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50].strip("-") or "web"


class WebSkill:
    def __init__(self, vault_path, researcher, save_folder: str = "NARA/Web"):
        self.vault_path = Path(vault_path)
        self.researcher = researcher  # callable(prompt: str) -> str
        self.save_folder = save_folder

    @classmethod
    def from_config(cls, cfg, researcher):
        return cls(
            cfg.get("vault.path"),
            researcher,
            save_folder=cfg.get("web.save_folder", "NARA/Web"),
        )

    def research(self, query: str) -> Path:
        text = self.researcher(
            f"Search the web about: {query}\n\nWrite a concise summary as 5-8 bullet "
            "points, then list the source URLs at the end."
        )
        return self._save(query, text, source=query)

    def summarize_url(self, url: str) -> Path:
        text = self.researcher(
            f"Fetch this page and summarize its key points in a few bullets, then "
            f"note the source URL:\n{url}"
        )
        return self._save(url, text, source=url)

    def _save(self, title: str, text: str, source: str) -> Path:
        folder = self.vault_path / self.save_folder
        folder.mkdir(parents=True, exist_ok=True)
        now = datetime.now().astimezone()
        path = folder / f"{now:%Y-%m-%d}_{_slug(title)}.md"
        header = f"# {title}\n\n_Source: {source} · saved {now:%Y-%m-%d %H:%M}_\n\n"
        path.write_text(header + (text or "").strip() + "\n", encoding="utf-8")
        return path
