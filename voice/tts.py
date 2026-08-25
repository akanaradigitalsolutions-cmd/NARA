"""Text-to-speech.

Implemented in **Phase 4**. A pluggable TTS interface with backends: "kokoro"
(local, needs espeak-ng), "macos" (say / AVSpeechSynthesizer, free), and
"elevenlabs" (premium cloud voice). Streams playback and supports ``stop()``
for barge-in.
"""
