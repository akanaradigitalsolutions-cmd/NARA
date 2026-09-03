/* ───────────────────────────────────────────────────────────────────────────
   NaraSocket (UI Phase 3) — the HUD's link to the backend service.

   Connects to /ws on the same origin (falls back to 127.0.0.1:8765 when the page
   is opened from file://), auto-reconnects, and relays events to handlers:
   onOpen, onClose, onEvent({type, ...}). send(message) forwards a user turn.
   Everything degrades quietly when the service isn't running — the demo controls
   still work offline.
   ─────────────────────────────────────────────────────────────────────────── */
(function (global) {
  "use strict";

  function wsUrl() {
    const loc = global.location;
    if (loc && (loc.protocol === "http:" || loc.protocol === "https:")) {
      const scheme = loc.protocol === "https:" ? "wss" : "ws";
      return scheme + "://" + loc.host + "/ws";
    }
    return "ws://127.0.0.1:8765/ws"; // file:// fallback → local service
  }

  function NaraSocket(handlers) {
    this.h = handlers || {};
    this.url = wsUrl();
    this.ws = null;
    this._retry = null;
    this._closed = false;
  }

  NaraSocket.prototype.connect = function () {
    this._closed = false;
    let ws;
    try {
      ws = new WebSocket(this.url);
    } catch (_) {
      this._scheduleRetry();
      return;
    }
    this.ws = ws;
    ws.onopen = () => this.h.onOpen && this.h.onOpen();
    ws.onclose = () => {
      this.ws = null;
      if (this.h.onClose) this.h.onClose();
      this._scheduleRetry();
    };
    ws.onerror = () => {}; // close handler drives reconnect
    ws.onmessage = (e) => {
      let msg;
      try {
        msg = JSON.parse(e.data);
      } catch (_) {
        return;
      }
      if (this.h.onEvent) this.h.onEvent(msg);
    };
  };

  NaraSocket.prototype._scheduleRetry = function () {
    if (this._closed || this._retry) return;
    this._retry = setTimeout(() => {
      this._retry = null;
      this.connect();
    }, 4000);
  };

  NaraSocket.prototype.send = function (message) {
    if (this.ws && this.ws.readyState === 1) {
      this.ws.send(JSON.stringify({ message: message }));
      return true;
    }
    return false;
  };

  NaraSocket.prototype.close = function () {
    this._closed = true;
    if (this._retry) {
      clearTimeout(this._retry);
      this._retry = null;
    }
    if (this.ws) this.ws.close();
  };

  global.NaraSocket = NaraSocket;
})(window);
