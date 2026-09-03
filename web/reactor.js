/* ───────────────────────────────────────────────────────────────────────────
   NARA Reactor Core — the living central element (UI Phase 2).

   A single Canvas 2D component driven by setState(name). It composes, centre-out:
   bloom → outer segmented HUD ring → inner ticked rings → radial reactive band →
   breathing core. Every state has its own colour, energy, breath, ring speed and
   band behaviour; parameters are eased frame-to-frame so the core *flows* between
   states rather than cutting.

   Real mic/TTS amplitude arrives in UI Phase 3 (Web Audio); until then the band
   is synthesised per state so the motion still maps to what NARA is "doing".
   Honours prefers-reduced-motion (renders a calm static frame, no RAF loop) and
   pauses when the window is hidden/blurred.
   ─────────────────────────────────────────────────────────────────────────── */
(function (global) {
  "use strict";

  const BAR_COUNT = 64; // design cap
  const TAU = Math.PI * 2;

  // Per-state target parameters. Colours are original arc-reactor tokens.
  const STATES = {
    offline:   { col: [74, 101, 119],  energy: 0.05, breath: 0.010, breathHz: 0.25, ring: 0.03, band: "off",     alpha: 0.55 },
    booting:   { col: [0, 229, 255],   energy: 0.38, breath: 0.060, breathHz: 0.90, ring: 0.65, band: "idle",    alpha: 1.0 },
    idle:      { col: [0, 229, 255],   energy: 0.28, breath: 0.055, breathHz: 0.50, ring: 0.12, band: "idle",    alpha: 1.0 },
    listening: { col: [56, 189, 248],  energy: 0.72, breath: 0.100, breathHz: 1.10, ring: 0.26, band: "listen",  alpha: 1.0 },
    thinking:  { col: [47, 107, 255],  energy: 0.82, breath: 0.060, breathHz: 0.80, ring: 0.85, band: "think",   alpha: 1.0 },
    speaking:  { col: [0, 229, 255],   energy: 0.78, breath: 0.085, breathHz: 1.45, ring: 0.30, band: "speak",   alpha: 1.0 },
    executing: { col: [255, 176, 32],  energy: 0.70, breath: 0.040, breathHz: 0.60, ring: 0.42, band: "execute", alpha: 1.0 },
    alert:     { col: [255, 59, 78],   energy: 0.92, breath: 0.120, breathHz: 3.00, ring: 0.22, band: "alert",   alpha: 1.0 },
  };

  const lerp = (a, b, t) => a + (b - a) * t;

  function Reactor(canvas, opts) {
    opts = opts || {};
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.reduced = !!opts.reducedMotion;
    this.stateName = "offline";

    // cur = what's drawn now; tgt = where we're easing to.
    const s = STATES.offline;
    this.cur = { col: s.col.slice(), energy: s.energy, breath: s.breath, breathHz: s.breathHz, ring: s.ring, alpha: s.alpha };
    this.tgt = Object.assign({}, this.cur, { col: s.col.slice() });
    this.band = "off";

    this.t = 0;                 // animation clock (seconds)
    this.ringAngle = 0;         // accumulated ring rotation
    this.sweep = 0;             // thinking sweep position
    this.exec = 0;              // executing progress 0..1
    this.amp = new Float32Array(BAR_COUNT); // smoothed band amplitudes
    this._raf = null;
    this._last = 0;

    this._resize = this._resize.bind(this);
    this._frame = this._frame.bind(this);
    window.addEventListener("resize", this._resize);
    this._bindVisibility();
    this._resize();
  }

  Reactor.prototype.setState = function (name) {
    const s = STATES[name] || STATES.idle;
    this.stateName = name;
    this.tgt.col = s.col.slice();
    this.tgt.energy = s.energy;
    this.tgt.breath = s.breath;
    this.tgt.breathHz = s.breathHz;
    this.tgt.ring = s.ring;
    this.tgt.alpha = s.alpha;
    this.band = s.band;
    if (name === "executing") this.exec = 0;
    if (this.reduced) {
      Object.assign(this.cur, { energy: s.energy, breath: s.breath, breathHz: s.breathHz, ring: s.ring, alpha: s.alpha });
      this.cur.col = s.col.slice();
      this._renderStatic();
    }
  };

  Reactor.prototype.start = function () {
    if (this.reduced) { this._renderStatic(); return; }
    if (this._raf) return;
    this._last = performance.now();
    this._raf = requestAnimationFrame(this._frame);
  };

  Reactor.prototype.stop = function () {
    if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null; }
  };

  // ── internals ────────────────────────────────────────────────────────────
  Reactor.prototype._bindVisibility = function () {
    const onHide = () => { if (document.hidden) this.stop(); else this.start(); };
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("blur", () => this.stop());
    window.addEventListener("focus", () => this.start());
  };

  Reactor.prototype._resize = function () {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = this.canvas.getBoundingClientRect();
    const size = Math.max(120, Math.min(rect.width, rect.height) || rect.width || 320);
    this.canvas.width = Math.round(size * dpr);
    this.canvas.height = Math.round(size * dpr);
    this.dpr = dpr;
    this.size = size;
    if (this.reduced) this._renderStatic();
  };

  Reactor.prototype._frame = function (now) {
    const dt = Math.min(0.05, (now - this._last) / 1000);
    this._last = now;
    this.t += dt;

    // Ease current params toward target (~380ms feel).
    const k = 1 - Math.pow(0.0025, dt); // frame-rate independent smoothing
    const c = this.cur, g = this.tgt;
    c.energy = lerp(c.energy, g.energy, k);
    c.breath = lerp(c.breath, g.breath, k);
    c.breathHz = lerp(c.breathHz, g.breathHz, k);
    c.ring = lerp(c.ring, g.ring, k);
    c.alpha = lerp(c.alpha, g.alpha, k);
    for (let i = 0; i < 3; i++) c.col[i] = lerp(c.col[i], g.col[i], k);

    this.ringAngle += c.ring * dt;
    this.sweep += dt * 2.2;
    this.exec = (this.exec + dt / 4) % 1; // ~4s progress loop

    this._updateBand(dt);
    this._draw();
    this._raf = requestAnimationFrame(this._frame);
  };

  // Synthesised per-state amplitudes (real audio replaces this in UI Phase 3).
  Reactor.prototype._updateBand = function (dt) {
    const t = this.t, mode = this.band;
    const target = (i) => {
      const a = (i / BAR_COUNT) * TAU;
      switch (mode) {
        case "idle":
          return 0.05 + 0.035 * (0.5 + 0.5 * Math.sin(t * 1.6 + i * 0.5));
        case "listen":
          return 0.18 + 0.16 * Math.abs(Math.sin(t * 3.0 + i * 0.4))
                       + 0.10 * (0.5 + 0.5 * Math.sin(t * 7.3 + i));
        case "speak": {
          const env = 0.35 + 0.45 * Math.max(0, Math.sin(t * 5.0));
          return env * (0.5 + 0.5 * Math.sin(t * 6.0 + i * 0.6));
        }
        case "think": {
          let d = Math.abs(((a - this.sweep) % TAU));
          if (d > Math.PI) d = TAU - d;
          return 0.08 + 0.55 * Math.exp(-(d * d) * 3.0);
        }
        case "execute":
          return 0.07 + 0.03 * Math.sin(t * 4 + i);
        case "alert":
          return 0.16 + 0.5 * (0.5 + 0.5 * Math.sin(t * 12));
        default:
          return 0.02;
      }
    };
    const s = 1 - Math.pow(0.02, dt); // smooth toward target
    for (let i = 0; i < BAR_COUNT; i++) this.amp[i] = lerp(this.amp[i], target(i), s);
  };

  Reactor.prototype._rgba = function (col, a) {
    return "rgba(" + (col[0] | 0) + "," + (col[1] | 0) + "," + (col[2] | 0) + "," + a + ")";
  };

  Reactor.prototype._draw = function () {
    const ctx = this.ctx, c = this.cur;
    const W = this.canvas.width, H = this.canvas.height;
    const R = Math.min(W, H) / 2;
    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.translate(W / 2, H / 2);
    ctx.globalAlpha = c.alpha;

    const breathe = 1 + c.breath * Math.sin(this.t * c.breathHz * TAU);

    this._drawBloom(ctx, R, c);
    this._drawOuterRing(ctx, R * 0.80, c);
    this._drawTickRing(ctx, R * 0.62, 48, c, 1);
    this._drawTickRing(ctx, R * 0.50, 3, c, -1); // 3 bold segments, counter-rotating
    this._drawBand(ctx, R * 0.30, R * 0.16, c);
    if (this.band === "execute") this._drawProgress(ctx, R * 0.30, c);
    this._drawCore(ctx, R * 0.15 * breathe, c);

    ctx.restore();
  };

  Reactor.prototype._drawBloom = function (ctx, R, c) {
    const g = ctx.createRadialGradient(0, 0, 0, 0, 0, R * 0.95);
    const e = c.energy;
    g.addColorStop(0, this._rgba(c.col, 0.22 * e));
    g.addColorStop(0.4, this._rgba(c.col, 0.10 * e));
    g.addColorStop(1, this._rgba(c.col, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(0, 0, R * 0.95, 0, TAU);
    ctx.fill();
  };

  Reactor.prototype._drawOuterRing = function (ctx, r, c) {
    const segs = 40, gap = 0.35;
    ctx.save();
    ctx.rotate(this.ringAngle * 0.6);
    ctx.lineWidth = Math.max(1, r * 0.012);
    ctx.strokeStyle = this._rgba(c.col, 0.35 + 0.3 * c.energy);
    for (let i = 0; i < segs; i++) {
      const a0 = (i / segs) * TAU;
      ctx.beginPath();
      ctx.arc(0, 0, r, a0, a0 + (TAU / segs) * (1 - gap));
      ctx.stroke();
    }
    ctx.restore();
  };

  Reactor.prototype._drawTickRing = function (ctx, r, ticks, c, dir) {
    ctx.save();
    ctx.rotate(this.ringAngle * dir);
    ctx.strokeStyle = this._rgba(c.col, 0.5);
    ctx.lineWidth = Math.max(1, r * 0.02);
    ctx.globalAlpha *= 0.9;
    // ring
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, TAU);
    ctx.strokeStyle = this._rgba(c.col, 0.18);
    ctx.stroke();
    // ticks
    ctx.strokeStyle = this._rgba(c.col, 0.6);
    for (let i = 0; i < ticks; i++) {
      const a = (i / ticks) * TAU;
      const len = ticks > 10 ? r * 0.06 : r * 0.16;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * r, Math.sin(a) * r);
      ctx.lineTo(Math.cos(a) * (r + len), Math.sin(a) * (r + len));
      ctx.stroke();
    }
    ctx.restore();
  };

  Reactor.prototype._drawBand = function (ctx, rInner, maxLen, c) {
    ctx.save();
    ctx.lineWidth = Math.max(1.5, rInner * 0.06);
    ctx.lineCap = "round";
    for (let i = 0; i < BAR_COUNT; i++) {
      const a = (i / BAR_COUNT) * TAU - Math.PI / 2;
      const len = maxLen * Math.min(1.4, this.amp[i]);
      const x0 = Math.cos(a) * rInner, y0 = Math.sin(a) * rInner;
      const x1 = Math.cos(a) * (rInner + len), y1 = Math.sin(a) * (rInner + len);
      ctx.strokeStyle = this._rgba(c.col, 0.35 + 0.5 * Math.min(1, this.amp[i] * 1.4));
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1, y1);
      ctx.stroke();
    }
    ctx.restore();
  };

  Reactor.prototype._drawProgress = function (ctx, r, c) {
    ctx.save();
    ctx.lineWidth = Math.max(2, r * 0.10);
    ctx.lineCap = "round";
    ctx.strokeStyle = this._rgba(c.col, 0.9);
    ctx.beginPath();
    ctx.arc(0, 0, r * 1.5, -Math.PI / 2, -Math.PI / 2 + TAU * this.exec);
    ctx.stroke();
    ctx.restore();
  };

  Reactor.prototype._drawCore = function (ctx, r, c) {
    const g = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
    g.addColorStop(0, "rgba(255,255,255," + (0.85 * c.alpha) + ")");
    g.addColorStop(0.35, this._rgba(c.col, 0.95));
    g.addColorStop(1, this._rgba(c.col, 0.15));
    ctx.fillStyle = g;
    ctx.shadowColor = this._rgba(c.col, 0.8);
    ctx.shadowBlur = r * (1.2 + c.energy);
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, TAU);
    ctx.fill();
  };

  // Calm single frame for reduced-motion users.
  Reactor.prototype._renderStatic = function () {
    if (!this.ctx) return;
    // seed a gentle static band so it isn't empty
    for (let i = 0; i < BAR_COUNT; i++) this.amp[i] = 0.12 + 0.03 * Math.sin(i);
    this._draw();
  };

  global.Reactor = Reactor;
})(window);
