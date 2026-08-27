"""Push-to-talk voice loop for NARA (Phase 4).

Press Enter, speak, and NARA transcribes → thinks → speaks the answer back.
Always-on wake-word ("Hey Nara") is an optional upgrade (see voice/wake.py);
push-to-talk is the reliable default and needs no wake model.
"""
from __future__ import annotations

from rich.console import Console


def voice_loop(agent, stt, tts, console: Console | None = None) -> None:
    console = console or Console()
    name = agent.cfg.get("persona.name", "NARA")
    console.print(
        f"[bold cyan]{name} voice[/] — press [bold]Enter[/] to talk, Ctrl-C to quit."
    )
    while True:
        try:
            console.input("[green]● Enter, then speak…[/] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            return

        try:
            with console.status("[dim]listening…[/]", spinner="dots"):
                text = stt.listen()
        except Exception as exc:  # mic / whisper / missing deps
            console.print(
                f"[red]Voice input failed:[/] {exc}\n"
                "[dim]Set up voice: brew install portaudio && "
                "uv pip install -e '.[voice]'[/]"
            )
            continue

        if not text:
            if getattr(stt, "last_peak", 1.0) < 0.006:
                console.print(
                    "[yellow](only silence — is the mic allowed? System Settings → Privacy "
                    "& Security → Microphone → enable your terminal, then reopen it. "
                    "Test with: nara voice --check)[/]"
                )
            else:
                console.print("[dim](didn't catch that — speak a little louder and retry)[/]")
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
