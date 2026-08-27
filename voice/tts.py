"""Text-to-speech for NARA (Phase 4).

Pluggable backends behind a tiny interface. macOS ``say`` is the zero-setup
default (needs nothing installed); Kokoro (local) and ElevenLabs (cloud) are
optional upgrades. If no speech engine is available (e.g. not on macOS), TTS
degrades to printing the line so the loop still works.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Protocol


class TTS(Protocol):
    name: str

    def speak(self, text: str) -> None: ...

    def stop(self) -> None: ...


class MacTTS:
    """macOS ``say`` — built in, no install. Optional voice (e.g. "Daniel")."""

    def __init__(self, voice: str | None = None, rate: int | None = None, runner=None):
        self.voice = voice
        self.rate = rate
        self.name = "macos"
        self._proc = None
        self._runner = runner

    def command(self, text: str) -> list[str]:
        cmd = ["say"]
        if self.voice:
            cmd += ["-v", self.voice]
        if self.rate:
            cmd += ["-r", str(self.rate)]
        cmd.append(text)
        return cmd

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self._runner is None and shutil.which("say") is None:
            print(f"🔊 {text}")  # no TTS available — show the line instead
            return
        self.stop()
        runner = self._runner or (lambda cmd: subprocess.Popen(cmd))
        self._proc = runner(self.command(text))
        wait = getattr(self._proc, "wait", None)
        if callable(wait):
            wait()

    def stop(self) -> None:
        proc = self._proc
        if proc is not None:
            poll, term = getattr(proc, "poll", None), getattr(proc, "terminate", None)
            if callable(poll) and callable(term) and proc.poll() is None:
                term()
        self._proc = None


class _Unavailable:
    """Placeholder for a backend that isn't wired up yet — falls back cleanly."""

    def __init__(self, name: str, hint: str):
        self.name = name
        self._hint = hint
        self._fallback = MacTTS()

    def speak(self, text: str) -> None:
        self._fallback.speak(text)

    def stop(self) -> None:
        self._fallback.stop()


def build_tts(cfg) -> TTS:
    """Pick a TTS backend from ``voice.tts_engine`` (default macOS ``say``)."""
    engine = str(cfg.get("voice.tts_engine", "macos")).lower()
    if engine == "macos":
        return MacTTS(voice=cfg.get("voice.tts_voice"), rate=cfg.get("voice.tts_rate"))
    if engine in ("kokoro", "elevenlabs"):
        # Optional premium backends — not implemented yet; use macOS say for now.
        return _Unavailable(engine, f"{engine} TTS is a future upgrade")
    return MacTTS()
