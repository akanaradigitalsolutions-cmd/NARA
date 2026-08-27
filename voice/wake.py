"""Wake-word detection — "Hey Nara" (Phase 4, optional).

Push-to-talk (voice/loop.py) is NARA's reliable default and needs no wake model.
Always-on wake detection is an optional upgrade: install the ``[wake]`` extra
(openWakeWord) and implement ``WakeWord.wait()`` to block until the phrase is
heard, then hand off to STT. Left as a documented interface for now so the voice
loop can adopt it without changing its shape.
"""
from __future__ import annotations


class WakeWord:
    """Blocks until the wake phrase is detected. Implemented with the [wake] extra."""

    def __init__(self, phrase: str = "Hey Nara", engine: str = "openwakeword"):
        self.phrase = phrase
        self.engine = engine

    def wait(self) -> None:
        raise NotImplementedError(
            "Wake word is an optional upgrade. Install `.[wake]` (openWakeWord) "
            "and implement wait(); until then use push-to-talk (`nara voice`)."
        )
