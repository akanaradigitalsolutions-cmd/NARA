"""NARA orchestrator — the "consciousness" loop.

Phase 0: a stub entry point. It loads configuration, prints ``NARA online``,
and shows the resolved config plus a non-blocking preflight status. The real
routing/reasoning loop lands in Phase 2.

Run it with::

    python -m core.orchestrator
    # or, after `pip install -e .`:
    nara
"""
from __future__ import annotations

import os
import shutil

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import Config, load_config

console = Console()


def _status(ok: bool) -> Text:
    return Text("● ready", style="green") if ok else Text("○ not set", style="yellow")


def _config_table(cfg: Config) -> Table:
    table = Table(
        title="Resolved configuration",
        title_style="bold",
        header_style="bold cyan",
        expand=False,
    )
    table.add_column("Setting")
    table.add_column("Value", overflow="fold")

    rows = [
        ("Persona", cfg.get("persona.name", "NARA")),
        ("Wake word", cfg.get("persona.wake_word", "Hey Nara")),
        ("Voice model (resident)", cfg.get("models.voice_model", "—")),
        ("Local model (on demand)", cfg.get("models.local_model", "—")),
        ("Cloud model (default)", cfg.get("models.cloud_model", "—")),
        ("Embeddings", cfg.get("models.embedding_model", "—")),
        ("Vault path", str(cfg.get("vault.path", "—"))),
        ("Vector index", str(cfg.get("memory.index_path", "—"))),
        ("TTS engine", cfg.get("voice.tts_engine", "—")),
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
    else:  # cli / subscription
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


def main() -> None:
    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as exc:
        console.print(
            Panel(str(exc), title="[red]NARA failed to start[/]", border_style="red")
        )
        raise SystemExit(1) from None

    name = cfg.get("persona.name", "NARA")
    banner = Text(justify="center")
    banner.append(f"{name} online\n", style="bold cyan")
    banner.append("Neural Assistant · Responsive · Autonomous", style="dim")
    console.print(Panel.fit(banner, border_style="cyan"))
    console.print(_config_table(cfg))
    console.print(_preflight_table(cfg))
    console.print(
        "[dim]Phase 0 skeleton. Next: the Brain (Phase 1) and the text loop "
        "(Phase 2) — see README.md.[/]"
    )


if __name__ == "__main__":
    main()
