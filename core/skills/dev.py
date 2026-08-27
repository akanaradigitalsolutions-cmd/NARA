"""Dev skill — delegate coding tasks to Claude Code (Phase 3).

Runs Claude Code headless (`claude -p`) inside one of your project repos, on
your Claude Pro/Max subscription (no API key), with least-privilege
permissions, and reports what changed. It never uses
``--dangerously-skip-permissions``.

    from core.skills.dev import DevSkill
    dev = DevSkill.from_config(load_config())
    result = dev.run_task("relaxha", "add a /health endpoint")
    print(result.format())
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class DevError(RuntimeError):
    """Raised when a dev task cannot be run."""


@dataclass
class DevResult:
    project: str
    summary: str
    files_changed: list[str] = field(default_factory=list)
    cost_usd: float | None = None
    session_id: str | None = None
    over_budget: bool = False

    def format(self) -> str:
        lines = [self.summary.strip() or "(no summary)"]
        if self.files_changed:
            lines.append("")
            lines.append(f"Files changed ({len(self.files_changed)}):")
            lines += [f"  - {f}" for f in self.files_changed]
        if self.cost_usd:
            flag = "  ⚠ over budget" if self.over_budget else ""
            lines.append(f"\nCost: ${self.cost_usd:.4f}{flag}")
        return "\n".join(lines)


def _default_runner(args: list[str], cwd: Path, timeout: int):
    return subprocess.run(
        args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False
    )


def _parse_output(stdout: str) -> tuple[str, float | None, str | None]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout.strip(), None, None
    if isinstance(data, dict):
        summary = (data.get("result") or "").strip()
        return summary, data.get("total_cost_usd"), data.get("session_id")
    return str(data).strip(), None, None


def _git_changed(repo: Path) -> list[str]:
    """Files touched in ``repo`` per `git status --porcelain` (empty if not git)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    changed = []
    for line in proc.stdout.splitlines():
        path = line[3:].strip() if len(line) > 3 else line.strip()
        if path:
            changed.append(path)
    return changed


class DevSkill:
    """Delegate coding tasks to Claude Code, scoped to a named project repo."""

    def __init__(self, projects, binary="claude", max_cost_usd=2.0, timeout=1800, runner=None):
        self.projects = {k: Path(v).expanduser() for k, v in dict(projects or {}).items()}
        self.binary = binary
        self.max_cost_usd = max_cost_usd
        self.timeout = timeout
        self._runner = runner or _default_runner

    @classmethod
    def from_config(cls, cfg, runner=None) -> DevSkill:
        return cls(
            projects=cfg.get("dev.projects", {}) or {},
            max_cost_usd=cfg.get("dev.max_cost_usd", 2.0),
            timeout=cfg.get("dev.timeout_seconds", 1800),
            runner=runner,
        )

    def list_projects(self) -> dict[str, Path]:
        return dict(self.projects)

    def resolve(self, project: str) -> Path:
        key = project.strip().lower()
        for name, path in self.projects.items():
            if name.lower() == key:
                return path
        known = ", ".join(self.projects) or "(none configured — see dev.projects in config)"
        raise DevError(f"Unknown project '{project}'. Known projects: {known}.")

    def run_task(
        self,
        project: str,
        task: str,
        *,
        allow_bash: bool = False,
        dry_run: bool = False,
        session_id: str | None = None,
    ) -> DevResult:
        repo = self.resolve(project)
        if not repo.is_dir():
            raise DevError(f"Repo path for '{project}' does not exist: {repo}")

        args = [
            self.binary,
            "-p",
            task,
            "--output-format",
            "json",
            "--permission-mode",
            "plan" if dry_run else "acceptEdits",
        ]
        if allow_bash and not dry_run:
            args += ["--allowedTools", "Bash"]
        if session_id:
            args += ["--resume", session_id]

        try:
            proc = self._runner(args, repo, self.timeout)
        except FileNotFoundError as exc:
            raise DevError(
                "`claude` CLI not found. Install Claude Code and run `claude login`."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DevError(f"Claude Code timed out after {self.timeout}s") from exc

        if getattr(proc, "returncode", 1) != 0:
            stderr = (getattr(proc, "stderr", "") or "").strip()
            raise DevError(f"Claude Code exited {proc.returncode}: {stderr[:300]}")

        summary, cost, sid = _parse_output(getattr(proc, "stdout", "") or "")
        files = [] if dry_run else _git_changed(repo)
        over = bool(cost and cost > self.max_cost_usd)
        return DevResult(
            project=project,
            summary=summary,
            files_changed=files,
            cost_usd=cost,
            session_id=sid,
            over_budget=over,
        )

    def resume(self, project: str, task: str, session_id: str, *, allow_bash: bool = False):
        return self.run_task(project, task, allow_bash=allow_bash, session_id=session_id)
