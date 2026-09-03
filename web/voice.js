/* ───────────────────────────────────────────────────────────────────────────
   VoiceInput (UI Phase 3) — speech-to-text in the browser.

   Uses the Web Speech API (SpeechRecognition / webkitSpeechRecognition) so that
   when you talk, your words appear live in the transcript and, on a final
   result, are sent to NARA. This is separate from the reactor's band (which
   reads the mic for amplitude); together they make the "speak and see it" loop.

   Requires Chrome (or Safari) and a secure context — serve the HUD from
   http://127.0.0.1:8765/ui, not file://, or the browser blocks the mic.
   ─────────────────────────────────────────────────────────────────────────── */
(function (global) {
  "use strict";

  function VoiceInput(handlers) {
    this.h = handlers || {};
    const SR = global.SpeechRecognition || global.webkitSpeechRecognition;
    this.SR = SR;
    this.supported = !!SR;
    this.rec = null;
    this.listening = false;
  }

  VoiceInput.prototype.start = function () {
    if (!this.supported) {
      this._emit("onError", "no-speech-api");
      return false;
    }
    if (this.listening) return true;

    const rec = new this.SR();
    rec.lang = navigator.language || "en-US";
    rec.interimResults = true;   // live partial text
    rec.continuous = false;      // one utterance, then stop (push-to-talk)
    rec.maxAlternatives = 1;

    rec.onresult = (e) => {
      let interim = "";
      let final = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) final += r[0].transcript;
        else interim += r[0].transcript;
      }
      if (interim) this._emit("onPartial", interim);
      if (final) this._emit("onFinal", final.trim());
    };
    rec.onerror = (e) => this._emit("onError", (e && e.error) || "error");
    rec.onend = () => {
      this.listening = false;
      this._emit("onEnd");
    };

    try {
      rec.start();
    } catch (err) {
      this._emit("onError", String(err));
      return false;
    }
    this.rec = rec;
    this.listening = true;
    return true;
  };

  VoiceInput.prototype.stop = function () {
    if (this.rec) {
      try {
        this.rec.stop();
      } catch (_) {
        /* already stopped */
      }
    }
    this.listening = false;
  };

  VoiceInput.prototype._emit = function (name, arg) {
    if (typeof this.h[name] === "function") this.h[name](arg);
  };

  global.VoiceInput = VoiceInput;
})(window);
