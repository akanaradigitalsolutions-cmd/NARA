"""Wake-word detector — "Hey Nara".

Implemented in **Phase 4**. An always-on, low-CPU detector using openWakeWord
(pre-trained "Hey Jarvis" to start) or Picovoice Porcupine (custom "Hey Nara").
Fires an async event on detection so the loop starts listening.
"""
