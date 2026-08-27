"""Speech-to-text for NARA (Phase 4).

Records from the microphone until you stop talking (simple silence detection)
and transcribes with faster-whisper. The heavy imports (``sounddevice``,
``faster_whisper``) are lazy, so this module loads without the ``[voice]`` extra
installed — only ``listen()`` needs them.
"""
from __future__ import annotations

import numpy as np

DEFAULT_SAMPLE_RATE = 16000


def _rms(frame: np.ndarray) -> float:
    if frame.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(frame.astype(np.float32)))))


def _is_silent(frame: np.ndarray, threshold: float) -> bool:
    return _rms(frame) < threshold


class STT:
    """Microphone capture + faster-whisper transcription."""

    def __init__(
        self,
        model_size: str = "small",
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        silence_ms: int = 800,
        silence_threshold: float = 0.01,
        max_seconds: int = 30,
        prespeech_seconds: float = 6.0,
    ):
        self.model_size = model_size
        self.sample_rate = sample_rate
        self.silence_ms = silence_ms
        self.silence_threshold = silence_threshold
        self.max_seconds = max_seconds
        self.prespeech_seconds = prespeech_seconds
        self._model = None
        # Diagnostics from the last record() call.
        self.last_peak = 0.0
        self.last_started = False

    def _load(self):
        from faster_whisper import WhisperModel

        if self._model is None:
            self._model = WhisperModel(self.model_size, device="auto", compute_type="int8")
        return self._model

    def record(self) -> np.ndarray:
        """Record mono float32 audio until ~silence_ms of quiet after speech.

        Stops early if no speech is heard within ``prespeech_seconds`` so it
        doesn't sit through the full timeout on a silent or blocked mic. Records
        the peak level and whether speech started, for diagnostics.
        """
        import sounddevice as sd

        frame_ms = 30
        frame_len = int(self.sample_rate * frame_ms / 1000)
        silence_needed = max(1, self.silence_ms // frame_ms)
        prespeech_frames = int(self.prespeech_seconds * 1000 / frame_ms)
        max_frames = int(self.max_seconds * 1000 / frame_ms)

        collected: list[np.ndarray] = []
        silent_run = 0
        started = False
        peak = 0.0
        with sd.InputStream(
            samplerate=self.sample_rate, channels=1, dtype="float32", blocksize=frame_len
        ) as stream:
            for i in range(max_frames):
                frame, _overflow = stream.read(frame_len)
                frame = np.asarray(frame).reshape(-1)
                collected.append(frame)
                level = _rms(frame)
                peak = max(peak, level)
                if level >= self.silence_threshold:
                    started = True
                    silent_run = 0
                elif started:
                    silent_run += 1
                    if silent_run >= silence_needed:
                        break
                elif i >= prespeech_frames:
                    break  # nothing said yet — stop waiting

        self.last_peak = peak
        self.last_started = started
        if not collected:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(collected)

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        model = self._load()
        segments, _info = model.transcribe(audio, language=None)
        return " ".join(seg.text.strip() for seg in segments).strip()

    def listen(self) -> str:
        audio = self.record()
        if not self.last_started:
            return ""  # no speech detected — skip transcription
        return self.transcribe(audio)

    def mic_level(self, seconds: float = 2.0) -> float:
        """Record for a fixed time and return the peak RMS level (mic self-test)."""
        import sounddevice as sd

        frame_ms = 30
        frame_len = int(self.sample_rate * frame_ms / 1000)
        frames = int(seconds * 1000 / frame_ms)
        peak = 0.0
        with sd.InputStream(
            samplerate=self.sample_rate, channels=1, dtype="float32", blocksize=frame_len
        ) as stream:
            for _ in range(frames):
                frame, _overflow = stream.read(frame_len)
                peak = max(peak, _rms(np.asarray(frame).reshape(-1)))
        self.last_peak = peak
        return peak


def build_stt(cfg) -> STT:
    return STT(
        model_size=cfg.get("voice.stt_model", "small"),
        silence_ms=cfg.get("voice.silence_ms", 800),
        silence_threshold=cfg.get("voice.silence_threshold", 0.01),
        prespeech_seconds=cfg.get("voice.prespeech_seconds", 6.0),
    )
