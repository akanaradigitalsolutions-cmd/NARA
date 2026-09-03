"""NARA orchestrator — the "consciousness" loop (Phase 2).

Runs the text agent: retrieve vault memory -> route -> answer (local Ollama by
default, cloud Claude for hard/long requests) -> remember salient facts. Usage::

    nara                     # chat REPL
    nara --once "hello"      # single turn, then exit
    nara --status            # config + preflight, then exit
    python -m core.orchestrator
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import Config, load_config
from .doctor import exit_code, run_checks, worst
from .engines import Engine, EngineError, Reply, build_cloud_engine, build_local_engine
from .logging_setup import setup_logging
from .memory import MemoryManager
from .persona import build_system_prompt, format_memory
from .router import Router
from .skills import skill_specs
from .skills.content import ContentSkill
from .skills.dev import DevError, DevSkill
from .skills.macos import MacControl
from .skills.web import WebSkill
from .usage import UsageLog, budget_status

console = Console()

_REMEMBER_RE = re.compile(
    r"^\s*(?:please\s+)?(?:remember|note|make a note)(?:\s+that|\s+this)?\s*:?\s+(.+)",
    re.IGNORECASE | re.DOTALL,
)


# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────
class Agent:
    """NARA's text agent: memory-grounded, model-routed conversation."""

    def __init__(
        self,
        cfg: Config,
        memory: MemoryManager,
        router: Router,
        local_engine: Engine,
        cloud_engine: Engine,
        *,
        history_turns: int = 6,
        memory_k: int = 6,
    ):
        self.cfg = cfg
        self.memory = memory
        self.router = router
        self.local_engine = local_engine
        self.cloud_engine = cloud_engine
        self.history_turns = history_turns
        self.memory_k = memory_k
        self.history: list[dict] = []
        self.usage = UsageLog.from_config(cfg)
        self.escalate_low_conf = cfg.get("router.escalate_low_confidence", True)

    @classmethod
    def from_config(
        cls,
        cfg: Config | None = None,
        *,
        memory: MemoryManager | None = None,
        local_engine: Engine | None = None,
        cloud_engine: Engine | None = None,
    ) -> Agent:
        cfg = cfg or load_config()
        return cls(
            cfg,
            memory or MemoryManager.from_config(cfg),
            Router.from_config(cfg),
            local_engine or build_local_engine(cfg),
            cloud_engine or build_cloud_engine(cfg),
            history_turns=cfg.get("agent.history_turns", 6),
            memory_k=cfg.get("agent.memory_k", cfg.get("memory.search_k", 6)),
        )

    def _safe_search(self, query: str):
        try:
            return self.memory.search(query, k=self.memory_k)
        except Exception:  # memory is best-effort — never break the chat over it
            return []

    def _maybe_remember(self, user_msg: str) -> Reply | None:
        match = _REMEMBER_RE.match(user_msg)
        if not match:
            return None
        fact = match.group(1).strip()
        try:
            path = self.memory.remember(fact)
            return Reply(f"Noted — saved to {path.name}.", "memory", route="memory")
        except Exception as exc:
            return Reply(f"I couldn't save that: {exc}", "memory", route="memory")

    def run(self, user_msg: str) -> Reply:
        remembered = self._maybe_remember(user_msg)
        if remembered is not None:
            self._record(remembered, 0, user_msg)
            return remembered

        memory_block = format_memory(self._safe_search(user_msg))
        private = self.router.is_private(user_msg)
        route = "local" if private else self.router.classify(user_msg, context=memory_block)

        system = build_system_prompt(self.cfg)
        if memory_block:
            system = f"{system}\n\n{memory_block}"
        window = self.history[-2 * self.history_turns :]
        messages = [*window, {"role": "user", "content": user_msg}]

        start = time.perf_counter()
        reply = self._answer(route, system, messages, private=private)
        latency_ms = int((time.perf_counter() - start) * 1000)

        self._record(reply, latency_ms, user_msg)
        self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": reply.text})
        return reply

    def _answer(self, route: str, system: str, messages: list[dict], *, private: bool) -> Reply:
        # Budget guard: over the monthly cloud cap -> answer locally.
        if route in ("cloud", "dev") and not self._cloud_allowed():
            local = self._safe_generate(self.local_engine, system, messages)
            if local is not None:
                local.route = "local"
                local.text = "(monthly cloud budget reached — answering locally)\n" + local.text
                return local
            route = "cloud"  # local unavailable; try cloud anyway

        primary = self.local_engine if route == "local" else self.cloud_engine
        alternate = self.cloud_engine if route == "local" else self.local_engine
        reply = self._safe_generate(primary, system, messages)
        if reply is None:
            reply = self._safe_generate(alternate, system, messages)
            if reply is None:
                return Reply("Both engines are unavailable right now.", "none", route=route)
            reply.route = "local" if alternate is self.local_engine else "cloud"
            reply.text = f"({primary.name} unavailable — via {alternate.name})\n{reply.text}"
            return reply

        reply.route = route
        # Confidence escalation: an unsure LOCAL answer goes up to the cloud.
        if (
            route == "local"
            and not private
            and self.escalate_low_conf
            and self.router.low_confidence(reply.text)
            and self._cloud_allowed()
        ):
            escalated = self._safe_generate(self.cloud_engine, system, messages)
            if escalated is not None:
                escalated.route = "cloud+esc"
                return escalated
        return reply

    def _safe_generate(self, engine: Engine, system: str, messages: list[dict]) -> Reply | None:
        try:
            return engine.generate(system, messages)
        except EngineError:
            return None

    def _cloud_allowed(self) -> bool:
        return not budget_status(self.cfg, self.usage)["over"]

    def _record(self, reply: Reply, latency_ms: int, user_msg: str) -> None:
        try:
            self.usage.record(
                reply.route or "?",
                reply.engine,
                latency_ms,
                reply.cost_usd or 0.0,
                len(user_msg),
                len(reply.text),
            )
        except Exception:  # usage logging must never break a reply
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Status / preflight (also the `nara --status` view)
# ─────────────────────────────────────────────────────────────────────────────
def _status(ok: bool) -> Text:
    return Text("● ready", style="green") if ok else Text("○ not set", style="yellow")


def _config_table(cfg: Config) -> Table:
    table = Table(
        title="Resolved configuration", title_style="bold", header_style="bold cyan"
    )
    table.add_column("Setting")
    table.add_column("Value", overflow="fold")
    rows = [
        ("Persona", cfg.get("persona.name", "NARA")),
        ("Local chat model", cfg.get("agent.local_model") or cfg.get("models.voice_model", "—")),
        ("Cloud backend", cfg.get("cloud.backend", "cli")),
        ("Cloud model", cfg.get("models.cloud_model", "—")),
        ("Embeddings", cfg.get("models.embedding_model", "—")),
        ("Vault path", str(cfg.get("vault.path", "—"))),
        ("Vector index", str(cfg.get("memory.index_path", "—"))),
        ("Config file", str(cfg.source)),
    ]
    for key, value in rows:
        table.add_row(key, str(value))
    return table


def _preflight_table(cfg: Config) -> Table:
    table = Table(title="Preflight", title_style="bold", header_style="bold cyan")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")

    backend = str(cfg.get("cloud.backend", "cli")).lower()
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if backend == "api":
        table.add_row(
            "Cloud auth · api",
            _status(has_key),
            "ANTHROPIC_API_KEY found" if has_key else "set ANTHROPIC_API_KEY in .env",
        )
    else:
        cli_path = shutil.which("claude")
        table.add_row(
            "Cloud auth · cli",
            _status(bool(cli_path)),
            f"claude CLI found ({cli_path}); run `claude login` with your Pro/Max plan"
            if cli_path
            else "install: npm i -g @anthropic-ai/claude-code, then `claude login`",
        )
        if has_key:
            table.add_row(
                "API key override",
                Text("● warning", style="bold yellow"),
                "ANTHROPIC_API_KEY is set — Claude Code will bill the API instead of "
                "your subscription. Unset it to use your plan.",
            )

    vault = cfg.get("vault.path")
    vault_ok = bool(vault) and os.path.isdir(str(vault))
    table.add_row(
        "Obsidian vault",
        _status(vault_ok),
        str(vault) if vault else "vault.path not configured",
    )
    table.add_row("Config", _status(True), str(cfg.source))
    return table


def show_status(cfg: Config) -> None:
    name = cfg.get("persona.name", "NARA")
    banner = Text(justify="center")
    banner.append(f"{name} online\n", style="bold cyan")
    banner.append("Neural Assistant · Responsive · Autonomous", style="dim")
    console.print(Panel.fit(banner, border_style="cyan"))
    console.print(_config_table(cfg))
    console.print(_preflight_table(cfg))


def show_stats(cfg: Config) -> None:
    usage = UsageLog.from_config(cfg)
    summary = usage.summary()
    budget = budget_status(cfg, usage)

    table = Table(title="NARA usage", title_style="bold", header_style="bold cyan")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Total requests", str(summary["total"]))
    if summary["total"]:
        local_pct = round(summary["local"] / summary["total"] * 100)
        table.add_row("Local", f"{summary['local']} ({local_pct}%)")
        table.add_row("Cloud", f"{summary['cloud']} ({100 - local_pct}%)")
    table.add_row("Avg latency", f"{summary['avg_latency_ms']} ms")
    table.add_row("Cost — all time", f"${summary['total_cost']:.4f}")
    table.add_row("Cost — this month", f"${summary['month_cost']:.4f}")
    if budget["cap"]:
        table.add_row(
            "Monthly budget",
            f"${budget['spend']:.2f} / ${budget['cap']:.2f} ({budget['percent']}%)",
        )
    console.print(table)

    if summary["by_engine"]:
        by_engine = Table(title="By engine", title_style="bold", header_style="bold cyan")
        by_engine.add_column("Engine")
        by_engine.add_column("Requests", justify="right")
        for engine, count in sorted(summary["by_engine"].items(), key=lambda kv: -kv[1]):
            by_engine.add_row(engine, str(count))
        console.print(by_engine)

    if budget["over"]:
        console.print(
            "[bold red]Over the monthly cloud budget — cloud calls fall back to local.[/]"
        )
    elif budget["warn"]:
        console.print(f"[yellow]Heads up: at {budget['percent']}% of the monthly cloud budget.[/]")


# ─────────────────────────────────────────────────────────────────────────────
# REPL
# ─────────────────────────────────────────────────────────────────────────────
def _print_reply(name: str, reply: Reply) -> None:
    console.print(f"[bold cyan]{name} ›[/] ", end="")
    console.print(reply.text or "(no reply)", markup=False, highlight=False)
    meta = reply.route or "?"
    extra = f" · ${reply.cost_usd:.4f}" if reply.cost_usd else ""
    console.print(f"[dim]{meta} · {reply.engine}{extra}[/]")


def repl(agent: Agent) -> None:
    cfg = agent.cfg
    name = cfg.get("persona.name", "NARA")
    banner = Text(justify="center")
    banner.append(f"{name} online\n", style="bold cyan")
    banner.append("chat  ·  /status  /help  /exit", style="dim")
    console.print(Panel.fit(banner, border_style="cyan"))

    while True:
        try:
            user = console.input("[bold green]you ›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            return
        if not user:
            continue
        if user in ("/exit", "/quit"):
            console.print("[dim]Goodbye.[/]")
            return
        if user == "/status":
            show_status(cfg)
            continue
        if user == "/stats":
            show_stats(cfg)
            continue
        if user == "/skills":
            show_skills(cfg)
            continue
        if user == "/doctor":
            show_doctor(cfg)
            continue
        if user.startswith("/dev"):
            rest = user[len("/dev") :].strip()
            parts = rest.split(maxsplit=1)
            if len(parts) < 2:
                console.print('[dim]Usage: /dev <project> "<task>"[/]')
                continue
            project, task = parts[0], parts[1]
            with console.status(f"[dim]Claude Code working in {project}…[/]", spinner="dots"):
                out = run_dev(cfg, project, task)
            console.print(out, markup=False, highlight=False)
            continue
        if user == "/help":
            console.print(
                "[dim]Chat normally. Commands: /status, /stats, /skills, /doctor, /help, "
                '/exit, /dev <project> "<task>". Say "remember that …" to save a fact.[/]'
            )
            continue
        with console.status("[dim]thinking…[/]", spinner="dots"):
            reply = agent.run(user)
        _print_reply(name, reply)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def run_dev(
    cfg: Config, project: str, task: str, *, allow_bash: bool = False, dry_run: bool = False
) -> str:
    """Delegate a coding task to Claude Code and return a formatted summary."""
    dev = DevSkill.from_config(cfg)
    try:
        result = dev.run_task(project, task, allow_bash=allow_bash, dry_run=dry_run)
    except DevError as exc:
        return f"[dev] {exc}"
    return result.format()


def run_voice(cfg: Config, check: bool = False) -> None:
    """Start the voice loop, or (``check``) run a quick microphone self-test."""
    from voice.stt import build_stt

    stt = build_stt(cfg)
    if check:
        console.print("[dim]Testing microphone for 2s — say something now…[/]")
        try:
            peak = stt.mic_level(2.0)
        except Exception as exc:
            console.print(
                f"[red]Mic error:[/] {exc}\n[dim]Grant your terminal Microphone access in "
                "System Settings → Privacy & Security, then reopen it.[/]"
            )
            return
        if peak >= 0.01:
            console.print(f"[green]Mic works ✓[/]  (peak level {peak:.4f})")
        else:
            console.print(
                f"[yellow]Very quiet[/] (peak {peak:.4f}). Enable Microphone for your "
                "terminal in System Settings → Privacy & Security → Microphone and reopen "
                "it, or check the input device isn't muted."
            )
        return

    from voice.loop import voice_loop
    from voice.tts import build_tts

    agent = Agent.from_config(cfg)
    voice_loop(agent, stt, build_tts(cfg))


# ─────────────────────────────────────────────────────────────────────────────
# Skills (Phase 7): macOS control · web research · content drafting
# ─────────────────────────────────────────────────────────────────────────────
def run_macos(cfg: Config, action: str, target: str | None = None) -> str:
    """Control macOS: open apps, run Shortcuts, set Focus, list Shortcuts."""
    mac = MacControl()
    action = action.lower()
    try:
        if action == "open":
            return mac.open_app(_need(target, 'nara macos open "<App>"'))
        if action == "shortcut":
            return mac.run_shortcut(_need(target, 'nara macos shortcut "<Name>"'))
        if action == "focus":
            return mac.set_focus(_need(target, 'nara macos focus "<Mode>"'))
        if action == "list":
            names = mac.list_shortcuts()
            if not names:
                return "No Shortcuts found."
            return "Shortcuts:\n" + "\n".join(f"  - {n}" for n in names)
        return f"Unknown macOS action '{action}'. Try: open | shortcut | focus | list."
    except RuntimeError as exc:
        return f"[macos] {exc}"


def _need(value: str | None, usage: str) -> str:
    if not value:
        raise RuntimeError(f"missing argument — usage: {usage}")
    return value


def run_web(cfg: Config, mode: str, query: str) -> str:
    """Research the web via the cloud engine and save a note to the vault."""
    engine = build_cloud_engine(cfg)

    def researcher(prompt: str) -> str:
        return engine.generate(
            "You are a precise research assistant. Be factual and cite sources.",
            [{"role": "user", "content": prompt}],
        ).text

    web = WebSkill.from_config(cfg, researcher)
    try:
        if mode.lower() == "url":
            path = web.summarize_url(query)
        else:
            path = web.research(query)
    except EngineError as exc:
        return f"[web] cloud engine unavailable: {exc}"
    return f"Saved research → {path}"


def run_draft(cfg: Config, topic: str, kind: str = "caption", bilingual: bool = False) -> str:
    """Draft marketing content grounded in the vault and save it."""
    memory = MemoryManager.from_config(cfg)
    engine = build_cloud_engine(cfg)
    content = ContentSkill.from_config(cfg, memory, engine)
    try:
        text, path = content.draft(topic, kind=kind, bilingual=bilingual)
    except EngineError as exc:
        return f"[draft] cloud engine unavailable: {exc}"
    return f"{text.strip()}\n\nsaved → {path}"


def show_skills(cfg: Config) -> None:
    table = Table(title="NARA skills", title_style="bold", header_style="bold cyan")
    table.add_column("Skill", style="bold")
    table.add_column("What it does", overflow="fold")
    table.add_column("Run it with", overflow="fold")
    for spec in skill_specs():
        table.add_row(spec["name"], spec["summary"], "\n".join(spec["commands"]))
    console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# Doctor — health check (Phase 8)
# ─────────────────────────────────────────────────────────────────────────────
_STATUS_STYLE = {"ok": ("● ok", "green"), "warn": ("● warn", "yellow"), "fail": ("● fail", "red")}


def show_doctor(cfg: Config) -> int:
    """Render the health check and return an exit code (1 if anything failed)."""
    checks = run_checks(cfg)
    table = Table(title="NARA doctor", title_style="bold", header_style="bold cyan")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail / fix", overflow="fold")
    for check in checks:
        label, colour = _STATUS_STYLE.get(check.status, ("?", "white"))
        # Build the cell as Text (no markup parsing) — hints contain [brackets].
        detail = Text(check.detail)
        if check.hint:
            if check.detail:
                detail.append("\n")
            detail.append(check.hint, style="dim")
        table.add_row(check.name, Text(label, style=colour), detail)
    console.print(table)

    overall = worst(checks)
    if overall == "fail":
        console.print("[bold red]Some checks failed — follow the fixes above.[/]")
    elif overall == "warn":
        console.print("[yellow]Mostly good — a few things could be better (fixes above).[/]")
    else:
        console.print("[bold green]All systems go — NARA is ready. ✦[/]")
    return exit_code(checks)


def _version() -> str:
    try:
        from importlib.metadata import version

        return version("nara")
    except Exception:
        return "0.1.0"


def _dispatch(cfg: Config, args) -> int:
    if args.cmd == "dev":
        console.print(f"[dim]Delegating to Claude Code in '{args.project}'…[/]")
        out = run_dev(
            cfg, args.project, args.task, allow_bash=args.allow_bash, dry_run=args.dry_run
        )
        console.print(out, markup=False, highlight=False)
        return 0
    if args.cmd == "voice":
        run_voice(cfg, check=args.check)
        return 0
    if args.cmd == "serve":
        from .service import main as serve_main

        serve_main()
        return 0
    if args.cmd == "menubar":
        from app.menubar import main as menubar_main

        menubar_main()
        return 0
    if args.cmd == "stats":
        show_stats(cfg)
        return 0
    if args.cmd == "macos":
        console.print(run_macos(cfg, args.action, args.target), markup=False, highlight=False)
        return 0
    if args.cmd == "web":
        console.print(f"[dim]Researching '{args.query}' via Claude…[/]")
        console.print(run_web(cfg, args.mode, args.query), markup=False, highlight=False)
        return 0
    if args.cmd == "draft":
        console.print(f"[dim]Drafting a {args.kind} about '{args.topic}' via Claude…[/]")
        out = run_draft(cfg, args.topic, kind=args.kind, bilingual=args.bilingual)
        console.print(out, markup=False, highlight=False)
        return 0
    if args.cmd == "skills":
        show_skills(cfg)
        return 0
    if args.cmd == "doctor":
        return show_doctor(cfg)
    if args.status:
        show_status(cfg)
        return 0

    agent = Agent.from_config(cfg)
    if args.once:
        reply = agent.run(args.once)
        console.print(reply.text, markup=False, highlight=False)
        return 0
    repl(agent)
    return 0


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="nara", description="NARA — your terminal assistant.")
    parser.add_argument("--status", action="store_true", help="show config + preflight, then exit")
    parser.add_argument("--once", metavar="MESSAGE", help="send one message and exit")
    sub = parser.add_subparsers(dest="cmd")
    p_dev = sub.add_parser("dev", help="delegate a coding task to Claude Code in a project repo")
    p_dev.add_argument("project", help="project name from dev.projects in config")
    p_dev.add_argument("task", help='the coding task, quoted (e.g. "add a /health route")')
    p_dev.add_argument("--allow-bash", action="store_true", help="also permit shell commands")
    p_dev.add_argument("--dry-run", action="store_true", help="plan only; don't edit files")
    p_voice = sub.add_parser("voice", help="hands-free push-to-talk voice loop (Phase 4)")
    p_voice.add_argument("--check", action="store_true", help="test the microphone and exit")
    sub.add_parser("serve", help="run the local HTTP service for UIs (Phase 5)")
    sub.add_parser("menubar", help="run the macOS menu-bar app (Phase 5)")
    sub.add_parser("stats", help="show local-vs-cloud usage and spend (Phase 6)")
    p_macos = sub.add_parser("macos", help="control macOS apps, Shortcuts and Focus (Phase 7)")
    p_macos.add_argument("action", help="open | shortcut | focus | list")
    p_macos.add_argument("target", nargs="?", help="app / Shortcut / Focus-mode name")
    p_web = sub.add_parser("web", help="research the web into your vault (Phase 7)")
    p_web.add_argument("mode", choices=["search", "url"], help="'search' a query or fetch a 'url'")
    p_web.add_argument("query", help="the search query, or the URL to summarize")
    p_draft = sub.add_parser("draft", help="draft marketing content from your vault (Phase 7)")
    p_draft.add_argument("topic", help="what to write about, quoted")
    p_draft.add_argument("--kind", default="caption", choices=["caption", "listing", "outreach"])
    p_draft.add_argument("--bilingual", action="store_true", help="Bahasa Indonesia + English")
    sub.add_parser("skills", help="list what NARA can do (Phase 7)")
    sub.add_parser("doctor", help="health-check your NARA setup (Phase 8)")
    parser.add_argument("--version", action="version", version=f"NARA {_version()}")
    args = parser.parse_args(argv)

    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as exc:
        console.print(
            Panel(str(exc), title="[red]NARA failed to start[/]", border_style="red")
        )
        raise SystemExit(1) from None

    setup_logging(cfg)
    try:
        code = _dispatch(cfg, args)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/]")
        return
    except Exception as exc:
        logging.getLogger("nara").exception("command failed: %s", args.cmd or "chat")
        console.print(
            Panel(
                str(exc) or exc.__class__.__name__,
                title="[red]Something went wrong[/]",
                border_style="red",
            )
        )
        console.print(
            "[dim]Details logged to ~/.nara/logs/nara.log — run `nara doctor` "
            "to check your setup.[/]"
        )
        raise SystemExit(1) from None
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
