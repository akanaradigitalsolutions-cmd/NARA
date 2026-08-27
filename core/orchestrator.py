"""NARA orchestrator — the "consciousness" loop (Phase 2).

Runs the text agent: retrieve vault memory -> route -> answer (local Ollama by
default, cloud Claude for hard/long requests) -> remember salient facts. Usage::

    nara                     # chat REPL
    nara --once "hello"      # single turn, then exit
    nara --status            # config + preflight, then exit
    python -m core.orchestrator
"""
from __future__ import annotations

import os
import re
import shutil

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import Config, load_config
from .engines import Engine, EngineError, Reply, build_cloud_engine, build_local_engine
from .memory import MemoryManager
from .persona import build_system_prompt, format_memory
from .router import Router
from .skills.dev import DevError, DevSkill

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
            return remembered

        memory_block = format_memory(self._safe_search(user_msg))
        route = self.router.classify(user_msg, context=memory_block)

        system = build_system_prompt(self.cfg)
        if memory_block:
            system = f"{system}\n\n{memory_block}"
        window = self.history[-2 * self.history_turns :]
        messages = [*window, {"role": "user", "content": user_msg}]

        primary = self.local_engine if route == "local" else self.cloud_engine
        alternate = self.cloud_engine if route == "local" else self.local_engine
        try:
            reply = primary.generate(system, messages)
        except EngineError:
            try:
                reply = alternate.generate(system, messages)
                reply.text = (
                    f"({primary.name} unavailable — answered via {alternate.name})\n"
                    f"{reply.text}"
                )
            except EngineError as exc:
                return Reply(f"Both engines are unavailable. {exc}", "none", route=route)
        reply.route = route

        self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": reply.text})
        return reply


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
                "[dim]Chat normally. Commands: /status, /help, /exit, "
                '/dev <project> "<task>". Say "remember that …" to save a fact.[/]'
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


def run_voice(cfg: Config) -> None:
    """Start the hands-free push-to-talk voice loop."""
    from voice.loop import voice_loop
    from voice.stt import build_stt
    from voice.tts import build_tts

    agent = Agent.from_config(cfg)
    voice_loop(agent, build_stt(cfg), build_tts(cfg))


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
    sub.add_parser("voice", help="hands-free push-to-talk voice loop (Phase 4)")
    sub.add_parser("serve", help="run the local HTTP service for UIs (Phase 5)")
    sub.add_parser("menubar", help="run the macOS menu-bar app (Phase 5)")
    args = parser.parse_args(argv)

    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as exc:
        console.print(
            Panel(str(exc), title="[red]NARA failed to start[/]", border_style="red")
        )
        raise SystemExit(1) from None

    if args.cmd == "dev":
        console.print(f"[dim]Delegating to Claude Code in '{args.project}'…[/]")
        out = run_dev(
            cfg, args.project, args.task, allow_bash=args.allow_bash, dry_run=args.dry_run
        )
        console.print(out, markup=False, highlight=False)
        return
    if args.cmd == "voice":
        run_voice(cfg)
        return
    if args.cmd == "serve":
        from .service import main as serve_main

        serve_main()
        return
    if args.cmd == "menubar":
        from app.menubar import main as menubar_main

        menubar_main()
        return
    if args.status:
        show_status(cfg)
        return

    agent = Agent.from_config(cfg)
    if args.once:
        reply = agent.run(args.once)
        console.print(reply.text, markup=False, highlight=False)
        return
    repl(agent)


if __name__ == "__main__":
    main()
