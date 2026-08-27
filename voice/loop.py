"""Push-to-talk voice loop for NARA (Phase 4).

Reliable manual control: press Enter to start recording, speak, and press Enter
again to stop. NARA then transcribes → thinks → speaks the answer. This avoids
auto silence-detection, which is finicky across mics and noisy rooms.
"""
from __future__ import annotations

import select
import sys

from rich.console import Console


def _enter_ready() -> bool:
    """True if a line (Enter) is waiting on stdin, without blocking."""
    try:
        return bool(select.select([sys.stdin], [], [], 0)[0])
    except (OSError, ValueError):
        return False


def _drain_stdin() -> None:
    while _enter_ready():
        sys.stdin.readline()


def _stop_on_enter() -> bool:
    if _enter_ready():
        sys.stdin.readline()
        return True
    return False


def voice_loop(agent, stt, tts, console: Console | None = None) -> None:
    console = console or Console()
    name = agent.cfg.get("persona.name", "NARA")
    console.print(
        f"[bold cyan]{name} voice[/] — press [bold]Enter[/] to start recording, "
        "[bold]Enter[/] again to stop. Ctrl-C to quit."
    )
    while True:
        try:
            console.input("[green]● Enter to start…[/] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            return

        console.print("[red]● recording…[/] [dim]speak, then press Enter to stop[/]")
        _drain_stdin()
        try:
            audio = stt.record_until(_stop_on_enter)
        except Exception as exc:  # mic / sounddevice / missing deps
            console.print(f"[red]Mic error:[/] {exc}\n[dim]Test it with: nara voice --check[/]")
            continue

        if not stt.last_started:
            console.print("[yellow](only silence — speak up, or check the mic input)[/]")
            continue

        with console.status("[dim]transcribing…[/]", spinner="dots"):
            try:
                text = stt.transcribe(audio)
            except Exception as exc:
                console.print(f"[red]Transcription failed:[/] {exc}")
                continue

        if not text:
            console.print("[dim](didn't catch any words — try again)[/]")
            continue

        console.print(f"[green]you ›[/] {text}")
        with console.status("[dim]thinking…[/]", spinner="dots"):
            reply = agent.run(text)
        console.print(f"[bold cyan]{name} ›[/] ", end="")
        console.print(reply.text, markup=False, highlight=False)
        try:
            tts.speak(reply.text)
        except Exception as exc:  # never let TTS crash the loop
            console.print(f"[dim](couldn't speak: {exc})[/]")
