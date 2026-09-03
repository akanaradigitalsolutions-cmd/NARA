/* ───────────────────────────────────────────────────────────────────────────
   NARA HUD controller (UI Phase 2).

   Owns the app state, keeps the DOM (labels, telemetry, [data-state]) in sync
   with the Reactor, runs a short power-on sequence, and provides demo controls
   (buttons + number keys) so you can watch the core move through all 8 states.
   In the finished app these state changes arrive from the backend over a
   websocket (UI Phase 3); the demo controls are just a scaffold.
   ─────────────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  const STATES = [
    "offline", "booting", "idle", "listening",
    "thinking", "speaking", "executing", "alert",
  ];

  // Which model NARA is honestly using in each state (routing from the blueprint).
  const MODEL_BY_STATE = {
    offline: "—",
    booting: "local 9B",
    idle: "local 9B",
    listening: "local 9B",
    thinking: "Sonnet 5",
    speaking: "local 9B",
    executing: "Opus 4.8",
    alert: "—",
  };

  const hud = document.getElementById("hud");
  const canvas = document.getElementById("reactor");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const el = {
    stateLabel: document.getElementById("stateLabel"),
    hudState: document.getElementById("hudState"),
    hudModel: document.getElementById("hudModel"),
    hudLatency: document.getElementById("hudLatency"),
    tModel: document.getElementById("tModel"),
    srLive: document.getElementById("srLive"),
    buttons: Array.from(document.querySelectorAll(".controls button")),
  };

  const reactor = new Reactor(canvas, { reducedMotion: reduced });
  reactor.start();

  let bootTimer = null;

  function setState(name) {
    if (STATES.indexOf(name) === -1) return;
    if (bootTimer && name !== "booting") { clearTimeout(bootTimer); bootTimer = null; }

    hud.dataset.state = name;
    reactor.setState(name);

    const upper = name.toUpperCase();
    el.stateLabel.textContent = upper;
    el.hudState.textContent = upper;

    const model = MODEL_BY_STATE[name] || "—";
    el.hudModel.textContent = model;
    el.tModel.textContent = model;
    // Latency stays "—" until real telemetry is wired in UI Phase 4.
    el.hudLatency.textContent = name === "thinking" ? "…" : "—";

    el.buttons.forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.set === name))
    );
    el.srLive.textContent = "NARA " + name;
  }

  // A modest power-on: offline → booting → idle. The full staged boot sequence
  // (grid draw-on, telemetry populating line by line, ignition) lands in UI Phase 4.
  function boot() {
    if (reduced) { setState("idle"); return; }
    setState("booting");
    bootTimer = setTimeout(() => setState("idle"), 1900);
  }

  // Demo controls.
  el.buttons.forEach((b) =>
    b.addEventListener("click", () => setState(b.dataset.set))
  );
  window.addEventListener("keydown", (e) => {
    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= STATES.length) setState(STATES[n - 1]);
  });

  // Deep-link a state for demos/testing, e.g. index.html#state=thinking.
  function stateFromHash() {
    const m = /state=([a-z]+)/i.exec(location.hash || "");
    return m && STATES.indexOf(m[1].toLowerCase()) !== -1 ? m[1].toLowerCase() : null;
  }
  window.addEventListener("hashchange", () => {
    const s = stateFromHash();
    if (s) setState(s);
  });

  const initial = stateFromHash();
  if (initial) setState(initial);
  else boot();
})();
