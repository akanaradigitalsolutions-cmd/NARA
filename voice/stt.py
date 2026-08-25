"""Speech-to-text.

Implemented in **Phase 4**. On wake, capture mic audio with ``sounddevice``,
stop on ~800 ms of silence (simple VAD), and transcribe with faster-whisper
(``small`` by default, configurable).
"""
