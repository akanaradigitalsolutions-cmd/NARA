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
    ):
        self.model_size = model_size
        self.sample_rate = sample_rate
        self.silence_ms = silence_ms
        self.silence_threshold = silence_threshold
        self.max_seconds = max_seconds
        self._model = None

    def _load(self):
        from faster_whisper import WhisperModel

        if self._model is None:
            self._model = WhisperModel(self.model_size, device="auto", compute_type="int8")
        return self._model

    def record(self) -> np.ndarray:
        """Record mono float32 audio until ~silence_ms of quiet after speech."""
        import sounddevice as sd

        frame_ms = 30
        frame_len = int(self.sample_rate * frame_ms / 1000)
        silence_needed = max(1, self.silence_ms // frame_ms)
        max_frames = int(self.max_seconds * 1000 / frame_ms)

        collected: list[np.ndarray] = []
        silent_run = 0
        started = False
        with sd.InputStream(
            samplerate=self.sample_rate, channels=1, dtype="float32", blocksize=frame_len
        ) as stream:
            for _ in range(max_frames):
                frame, _overflow = stream.read(frame_len)
                frame = np.asarray(frame).reshape(-1)
                collected.append(frame)
                if _is_silent(frame, self.silence_threshold):
                    if started:
                        silent_run += 1
                        if silent_run >= silence_needed:
                            break
                else:
                    started = True
                    silent_run = 0
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
        return self.transcribe(self.record())


def build_stt(cfg) -> STT:
    return STT(
        model_size=cfg.get("voice.stt_model", "small"),
        silence_ms=cfg.get("voice.silence_ms", 800),
        silence_threshold=cfg.get("voice.silence_threshold", 0.01),
    )
