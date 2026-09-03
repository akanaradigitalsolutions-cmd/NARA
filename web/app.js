/* ───────────────────────────────────────────────────────────────────────────
   NARA HUD controller (UI Phase 2 + 3).

   Ties the pieces together: the Reactor, the real microphone (band reactivity
   while listening), the streaming Transcript, and the backend websocket. Demo
   controls (buttons / keys 1–8) still drive the state machine; when the service
   is running, typing a message runs the real agent and the reply streams back
   with live model/latency/cost telemetry.
   ─────────────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  const STATES = [
    "offline", "booting", "idle", "listening",
    "thinking", "speaking", "executing", "alert",
  ];

  // Resting model guess per state (used for the demo; real turns override it).
  const MODEL_BY_STATE = {
    offline: "—", booting: "local 9B", idle: "local 9B", listening: "local 9B",
    thinking: "Sonnet 5", speaking: "local 9B", executing: "Opus 4.8", alert: "—",
  };

  function modelLabel(route, engine) {
    if (route === "local") return "local 9B";
    if (route === "dev") return "Claude Code";
    if (route === "memory") return "memory";
    return engine || route || "—";
  }

  const hud = document.getElementById("hud");
  const canvas = document.getElementById("reactor");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const el = {
    stateLabel: document.getElementById("stateLabel"),
    hudState: document.getElementById("hudState"),
    hudModel: document.getElementById("hudModel"),
    hudLatency: document.getElementById("hudLatency"),
    tModel: document.getElementById("tModel"),
    tLatency: document.getElementById("tLatency"),
    tCost: document.getElementById("tCost"),
    link: document.getElementById("link"),
    srLive: document.getElementById("srLive"),
    composer: document.getElementById("composer"),
    composerInput: document.getElementById("composerInput"),
    buttons: Array.from(document.querySelectorAll(".controls button")),
  };

  const reactor = new Reactor(canvas, { reducedMotion: reduced });
  const mic = new MicAnalyser();
  const transcript = new Transcript(document.getElementById("stream"), { reducedMotion: reduced });
  reactor.amplitudeProvider = (out) => mic.read(out);
  reactor.start();

  let bootTimer = null;
  let sessionCost = 0;

  function setState(name) {
    if (STATES.indexOf(name) === -1) return;
    if (bootTimer && name !== "booting") { clearTimeout(bootTimer); bootTimer = null; }

    hud.dataset.state = name;
    reactor.setState(name);

    // Mic is live only while listening (privacy) — start on enter, stop on leave.
    if (name === "listening") mic.start();
    else mic.stop();

    const upper = name.toUpperCase();
    el.stateLabel.textContent = upper;
    el.hudState.textContent = upper;

    const model = MODEL_BY_STATE[name] || "—";
    el.hudModel.textContent = model;
    el.tModel.textContent = model;
    el.hudLatency.textContent = name === "thinking" ? "…" : "—";

    el.buttons.forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.set === name))
    );
    el.srLive.textContent = "NARA " + name;
  }

  function telemetry(meta) {
    const model = modelLabel(meta.route, meta.engine);
    el.tModel.textContent = model;
    el.hudModel.textContent = model;
    if (meta.latency_ms != null) {
      el.tLatency.textContent = meta.latency_ms + " ms";
      el.hudLatency.textContent = meta.latency_ms + " ms";
    }
    sessionCost += meta.cost || 0;
    el.tCost.textContent = "$" + sessionCost.toFixed(4);
  }

  // ── Backend link ───────────────────────────────────────────────────────
  const socket = new NaraSocket({
    onOpen() {
      el.link.textContent = "● linked";
      el.link.classList.add("on");
      el.composerInput.placeholder = "Message NARA…";
    },
    onClose() {
      el.link.textContent = "○ offline";
      el.link.classList.remove("on");
      el.composerInput.placeholder = "start `nara serve` to chat…";
    },
    onEvent(msg) {
      if (msg.type === "state" && msg.state === "thinking") {
        setState("thinking");
      } else if (msg.type === "turn") {
        // Client owns speaking→idle so the reveal and the core stay in sync.
        setState("speaking");
        telemetry(msg);
        transcript.addNara(msg.text || "", () => setState("idle"));
      }
      // other state/end events are advisory; the client drives the visuals.
    },
  });
  socket.connect();

  el.composer.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = el.composerInput.value.trim();
    if (!text) return;
    el.composerInput.value = "";
    transcript.addUser(text);
    if (!socket.send(text)) {
      transcript.addNara(
        "I'm not linked to the service yet — open me from http://127.0.0.1:8765/ui " +
        "with `nara serve` running."
      );
    }
  });

  // ── Demo controls ──────────────────────────────────────────────────────
  el.buttons.forEach((b) =>
    b.addEventListener("click", () => setState(b.dataset.set))
  );
  window.addEventListener("keydown", (e) => {
    if (e.target === el.composerInput) return; // don't hijack typing
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

  function boot() {
    if (reduced) { setState("idle"); return; }
    setState("booting");
    bootTimer = setTimeout(() => setState("idle"), 1900);
  }

  const initial = stateFromHash();
  if (initial) setState(initial);
  else boot();
})();
