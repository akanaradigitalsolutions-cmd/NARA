"""Phase 4 tests: voice TTS/STT logic, fully offline (no mic, no whisper)."""
from __future__ import annotations

import numpy as np

from core.config import load_config
from voice.stt import STT, _is_silent, _rms, build_stt
from voice.tts import MacTTS, _Unavailable, build_tts


def test_mac_tts_command_basic():
    assert MacTTS().command("hi") == ["say", "hi"]


def test_mac_tts_command_with_voice_and_rate():
    assert MacTTS(voice="Daniel", rate=180).command("hi") == [
        "say", "-v", "Daniel", "-r", "180", "hi",
    ]


def test_mac_tts_speak_uses_runner():
    calls: list[list[str]] = []
    MacTTS(runner=lambda cmd: calls.append(cmd)).speak("hello there")
    assert calls == [["say", "hello there"]]


def test_mac_tts_speak_ignores_empty():
    calls: list[list[str]] = []
    MacTTS(runner=lambda cmd: calls.append(cmd)).speak("   ")
    assert calls == []


def test_build_tts_defaults_to_macos():
    assert build_tts(load_config()).name == "macos"


def test_unavailable_backend_has_name():
    assert _Unavailable("kokoro", "future").name == "kokoro"


def test_is_silent_thresholds():
    assert _is_silent(np.zeros(480, dtype=np.float32), 0.01) is True
    assert _is_silent(np.full(480, 0.5, dtype=np.float32), 0.01) is False


def test_rms_of_empty_is_zero():
    assert _rms(np.zeros(0, dtype=np.float32)) == 0.0


def test_build_stt_from_config():
    stt = build_stt(load_config())
    assert stt.model_size
    assert stt.sample_rate == 16000


def test_transcribe_empty_audio_returns_empty():
    assert STT().transcribe(np.zeros(0, dtype=np.float32)) == ""
