/* ───────────────────────────────────────────────────────────────────────────
   MicAnalyser (UI Phase 3) — real microphone amplitude for the reactor's band.

   getUserMedia → Web Audio AnalyserNode. read(out) fills a Float32Array with a
   symmetric spectrum (0..~1.3) so the radial band mirrors nicely around the core.
   Requires a secure context: serve the HUD from http://127.0.0.1:8765/ui (the
   `nara serve` LaunchAgent) rather than file:// so the mic is allowed.

   Privacy: the mic is only opened while NARA is in the listening state and is
   released the moment it leaves. read() returns false when inactive, so the
   reactor falls back to its synthesised band.
   ─────────────────────────────────────────────────────────────────────────── */
(function (global) {
  "use strict";

  function MicAnalyser() {
    this.active = false;
    this.starting = false;
    this.ctx = null;
    this.stream = null;
    this.analyser = null;
    this.bins = null;
  }

  MicAnalyser.prototype.start = async function () {
    if (this.active || this.starting) return this.active;
    this.starting = true;
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("getUserMedia unavailable (serve over http://127.0.0.1)");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const AC = global.AudioContext || global.webkitAudioContext;
      this.ctx = new AC();
      if (this.ctx.state === "suspended") await this.ctx.resume();
      const src = this.ctx.createMediaStreamSource(stream);
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.7;
      src.connect(this.analyser);
      this.bins = new Uint8Array(this.analyser.frequencyBinCount);
      this.stream = stream;
      this.active = true;
    } catch (err) {
      this.active = false;
      console.warn("[NARA] mic unavailable:", err && err.message ? err.message : err);
    } finally {
      this.starting = false;
    }
    return this.active;
  };

  MicAnalyser.prototype.read = function (out) {
    if (!this.active || !this.analyser) return false;
    this.analyser.getByteFrequencyData(this.bins);
    const n = out.length;
    const half = Math.floor(n / 2);
    const usable = Math.floor(this.bins.length * 0.75); // skip the empty top end
    for (let i = 0; i < half; i++) {
      const v = (this.bins[Math.floor((i / half) * usable)] / 255) * 1.3;
      out[i] = v;          // one side
      out[n - 1 - i] = v;  // mirror → symmetric ring
    }
    if (n % 2) out[half] = out[half - 1] || 0;
    return true;
  };

  MicAnalyser.prototype.stop = function () {
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    if (this.ctx && this.ctx.state !== "closed") this.ctx.close();
    this.stream = null;
    this.ctx = null;
    this.analyser = null;
    this.active = false;
  };

  global.MicAnalyser = MicAnalyser;
})(window);
