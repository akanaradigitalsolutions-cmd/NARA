"""Phase 3 tests: DevSkill (Claude Code delegation), fully offline.

A fake runner stands in for the `claude` CLI, so no real process is spawned.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.skills.dev import DevError, DevResult, DevSkill


def make_runner(stdout="", returncode=0, stderr="", side_effect=None):
    captured: dict = {}

    def runner(args, cwd, timeout):
        captured["args"] = list(args)
        captured["cwd"] = Path(cwd)
        if side_effect:
            side_effect(Path(cwd))
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    runner.captured = captured
    return runner


def test_resolve_unknown_project_raises(tmp_path):
    dev = DevSkill({"relaxha": str(tmp_path)})
    with pytest.raises(DevError):
        dev.resolve("nope")


def test_resolve_is_case_insensitive(tmp_path):
    dev = DevSkill({"Relaxha": str(tmp_path)})
    assert dev.resolve("relaxha") == Path(str(tmp_path))


def test_missing_repo_raises(tmp_path):
    dev = DevSkill({"r": str(tmp_path / "nope")}, runner=make_runner())
    with pytest.raises(DevError):
        dev.run_task("r", "do something")


def test_run_task_parses_result_and_cost(tmp_path):
    repo = tmp_path / "relaxha"
    repo.mkdir()
    runner = make_runner(
        stdout=json.dumps({"result": "Added endpoint.", "total_cost_usd": 0.0, "session_id": "s1"})
    )
    dev = DevSkill({"relaxha": str(repo)}, runner=runner)
    result = dev.run_task("relaxha", "add a /health endpoint")
    assert result.summary == "Added endpoint."
    assert result.session_id == "s1"
    args = runner.captured["args"]
    assert args[args.index("--permission-mode") + 1] == "acceptEdits"


def test_dry_run_uses_plan_mode(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    runner = make_runner(stdout=json.dumps({"result": "here's the plan"}))
    dev = DevSkill({"r": str(repo)}, runner=runner)
    result = dev.run_task("r", "refactor auth", dry_run=True)
    args = runner.captured["args"]
    assert args[args.index("--permission-mode") + 1] == "plan"
    assert result.files_changed == []


def test_detects_changed_files(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    def touch(cwd: Path):
        (cwd / "new.txt").write_text("hi", encoding="utf-8")

    runner = make_runner(stdout=json.dumps({"result": "done"}), side_effect=touch)
    dev = DevSkill({"r": str(repo)}, runner=runner)
    result = dev.run_task("r", "make a file")
    assert "new.txt" in result.files_changed


def test_over_budget_flag(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    runner = make_runner(stdout=json.dumps({"result": "x", "total_cost_usd": 5.0}))
    dev = DevSkill({"r": str(repo)}, max_cost_usd=1.0, runner=runner)
    assert dev.run_task("r", "x").over_budget is True


def test_nonzero_exit_raises(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    runner = make_runner(returncode=2, stderr="boom")
    dev = DevSkill({"r": str(repo)}, runner=runner)
    with pytest.raises(DevError):
        dev.run_task("r", "x")


def test_result_format():
    result = DevResult(project="r", summary="Did it.", files_changed=["a.py", "b.py"], cost_usd=0.5)
    out = result.format()
    assert "Did it." in out
    assert "a.py" in out and "b.py" in out
    assert "0.5000" in out
