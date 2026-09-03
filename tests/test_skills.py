"""Phase 7 tests: skills (macOS control · web research · content drafting).

Everything runs offline: MacControl takes an injectable runner, WebSkill an
injectable researcher, and ContentSkill an injectable memory + engine (EchoEngine
echoes the prompt back, so we can assert on how the prompt was built).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core import orchestrator
from core.config import Config
from core.engines import EchoEngine
from core.skills import skill_specs
from core.skills.content import ContentSkill
from core.skills.macos import MacControl
from core.skills.web import WebSkill


# ── MacControl ───────────────────────────────────────────────────────────────
def make_runner(output: str = "", error: Exception | None = None):
    calls: list[list[str]] = []

    def runner(cmd):
        calls.append(list(cmd))
        if error is not None:
            raise error
        return output

    runner.calls = calls
    return runner


def test_open_app_builds_applescript():
    runner = make_runner()
    mac = MacControl(runner=runner)
    assert mac.open_app("Safari") == "Opened Safari."
    assert runner.calls == [["osascript", "-e", 'tell application "Safari" to activate']]


def test_run_shortcut_uses_cli():
    runner = make_runner()
    mac = MacControl(runner=runner)
    out = mac.run_shortcut("Morning Routine")
    assert "Morning Routine" in out
    assert runner.calls == [["shortcuts", "run", "Morning Routine"]]


def test_set_focus_runs_named_shortcut():
    runner = make_runner()
    mac = MacControl(runner=runner)
    mac.set_focus("Work")
    assert runner.calls == [["shortcuts", "run", "Work"]]


def test_list_shortcuts_parses_lines():
    runner = make_runner(output="Morning\n  Evening  \n\nWork\n")
    mac = MacControl(runner=runner)
    assert mac.list_shortcuts() == ["Morning", "Evening", "Work"]


def test_runner_errors_propagate():
    runner = make_runner(error=RuntimeError("osascript boom"))
    mac = MacControl(runner=runner)
    with pytest.raises(RuntimeError, match="boom"):
        mac.open_app("Nope")


def test_default_runner_raises_on_nonzero(monkeypatch):
    from core.skills import macos

    def fake_run(cmd, capture_output, text, check):
        return SimpleNamespace(returncode=1, stdout="", stderr="not permitted")

    monkeypatch.setattr(macos.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="not permitted"):
        macos._osascript_runner(["osascript", "-e", "x"])


# ── WebSkill ─────────────────────────────────────────────────────────────────
def test_web_research_saves_note(tmp_path):
    seen: dict[str, str] = {}

    def researcher(prompt: str) -> str:
        seen["prompt"] = prompt
        return "- trend one\n- trend two\nhttps://example.com"

    web = WebSkill(tmp_path, researcher, save_folder="NARA/Web")
    path = web.research("bali spa trends")
    assert path.exists()
    assert path.parent == tmp_path / "NARA" / "Web"
    assert "bali spa trends" in seen["prompt"]
    body = path.read_text(encoding="utf-8")
    assert "trend one" in body and "Source: bali spa trends" in body


def test_web_summarize_url_passes_url(tmp_path):
    seen: dict[str, str] = {}

    def researcher(prompt: str) -> str:
        seen["prompt"] = prompt
        return "key point"

    web = WebSkill(tmp_path, researcher)
    path = web.summarize_url("https://example.com/page")
    assert "https://example.com/page" in seen["prompt"]
    assert "https://example.com/page" in path.read_text(encoding="utf-8")


def test_web_from_config_reads_save_folder(tmp_path):
    cfg = Config(
        {"vault": {"path": str(tmp_path)}, "web": {"save_folder": "Notes/Web"}}, Path("cfg")
    )

    def researcher(prompt: str) -> str:
        return "ok"

    web = WebSkill.from_config(cfg, researcher)
    assert web.save_folder == "Notes/Web"
    assert web.vault_path == tmp_path


# ── ContentSkill ─────────────────────────────────────────────────────────────
class _Note:
    def __init__(self, text: str):
        self.text = text


class _FakeMemory:
    def __init__(self, notes):
        self._notes = notes

    def search(self, query: str, k: int = 5):
        return self._notes


def test_content_draft_grounds_in_notes(tmp_path):
    memory = _FakeMemory([_Note("Relaxha: 90-min Balinese massage, 250k IDR, riverside.")])
    content = ContentSkill(tmp_path, memory, EchoEngine(), save_folder="NARA/Content")
    text, path = content.draft("weekend promo", kind="caption")
    assert path.exists()
    assert path.parent == tmp_path / "NARA" / "Content"
    # EchoEngine echoes the user prompt: it must carry the kind + the brief.
    assert "Instagram caption" in text
    assert "Balinese massage" in text


def test_content_draft_bilingual(tmp_path):
    content = ContentSkill(tmp_path, _FakeMemory([]), EchoEngine())
    text, _ = content.draft("laundry pickup", bilingual=True)
    assert "Bahasa Indonesia" in text


def test_content_draft_survives_memory_error(tmp_path):
    class _Boom:
        def search(self, *a, **k):
            raise RuntimeError("no index yet")

    content = ContentSkill(tmp_path, _Boom(), EchoEngine())
    text, path = content.draft("anything")
    assert path.exists()
    assert "no matching vault notes" in text


# ── Registry + orchestrator handlers ─────────────────────────────────────────
def test_skill_specs_registry():
    specs = skill_specs()
    names = {s["name"] for s in specs}
    assert {"dev", "macos", "web", "content"} <= names
    for spec in specs:
        assert spec["summary"] and spec["commands"]


def _cfg(tmp_path) -> Config:
    return Config(
        {
            "vault": {"path": str(tmp_path)},
            "memory": {"index_path": str(tmp_path / "index.lancedb")},
            "web": {"save_folder": "NARA/Web"},
            "content": {"save_folder": "NARA/Content", "search_k": 5},
            "cloud": {"backend": "cli"},
        },
        Path("cfg"),
    )


def test_run_web_saves_and_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "build_cloud_engine", lambda cfg: EchoEngine())
    out = orchestrator.run_web(_cfg(tmp_path), "search", "spa trends")
    assert "Saved research" in out
    assert list((tmp_path / "NARA" / "Web").glob("*.md"))


def test_run_draft_saves_and_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "build_cloud_engine", lambda cfg: EchoEngine())
    out = orchestrator.run_draft(_cfg(tmp_path), "weekend promo", kind="caption")
    assert "saved →" in out
    assert list((tmp_path / "NARA" / "Content").glob("*.md"))


def test_run_macos_missing_target_is_friendly(tmp_path):
    out = orchestrator.run_macos(_cfg(tmp_path), "open")
    assert out.startswith("[macos]") and "usage" in out


def test_run_macos_unknown_action(tmp_path):
    out = orchestrator.run_macos(_cfg(tmp_path), "teleport", "Mars")
    assert "Unknown macOS action" in out
