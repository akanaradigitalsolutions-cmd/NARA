/* ───────────────────────────────────────────────────────────────────────────
   Transcript (UI Phase 3) — the conversation stream.

   Glass cards: your turns muted/right, NARA's cyan-accented/left. NARA replies
   reveal with a light typewriter so text "streams" in as it arrives. All text is
   inserted as textContent (never innerHTML) — transcript content is untrusted.
   ─────────────────────────────────────────────────────────────────────────── */
(function (global) {
  "use strict";

  function Transcript(streamEl, opts) {
    this.el = streamEl;
    this.reduced = !!(opts && opts.reducedMotion);
    this._typing = null;
  }

  Transcript.prototype._bubble = function (who, cls) {
    const wrap = document.createElement("div");
    wrap.className = "bubble " + cls;
    const tag = document.createElement("span");
    tag.className = "who";
    tag.textContent = who;
    const p = document.createElement("p");
    wrap.appendChild(tag);
    wrap.appendChild(p);
    this.el.appendChild(wrap);
    this._scroll();
    return p;
  };

  Transcript.prototype.addUser = function (text) {
    this._bubble("YOU", "you").textContent = text;
  };

  // Live speech: show the partial transcript in a single updating bubble…
  Transcript.prototype.liveUser = function (text) {
    if (!this._liveUserP) this._liveUserP = this._bubble("YOU", "you partial");
    this._liveUserP.textContent = text;
    this._scroll();
  };

  // …then finalise it (or create a plain one if there was no partial).
  Transcript.prototype.commitUser = function (text) {
    if (this._liveUserP) {
      this._liveUserP.textContent = text;
      this._liveUserP.parentNode.classList.remove("partial");
      this._liveUserP = null;
    } else {
      this.addUser(text);
    }
  };

  // Add a NARA turn; reveals `text` progressively for a streaming feel.
  // `onDone` fires when the reveal completes (immediately under reduced motion).
  Transcript.prototype.addNara = function (text, onDone) {
    const p = this._bubble("NARA", "nara");
    const done = typeof onDone === "function" ? onDone : function () {};
    if (this.reduced || !text) {
      p.textContent = text || "";
      this._scroll();
      done();
      return;
    }
    if (this._typing) clearInterval(this._typing);
    let i = 0;
    const step = Math.max(2, Math.round(text.length / 60)); // ~60 frames
    this._typing = setInterval(() => {
      i = Math.min(text.length, i + step);
      p.textContent = text.slice(0, i);
      this._scroll();
      if (i >= text.length) {
        clearInterval(this._typing);
        this._typing = null;
        done();
      }
    }, 24);
  };

  // Live token-by-token API (for true streaming engines later).
  Transcript.prototype.begin = function (who, cls) {
    this._live = this._bubble(who, cls);
    return this._live;
  };
  Transcript.prototype.append = function (delta) {
    if (this._live) {
      this._live.textContent += delta;
      this._scroll();
    }
  };

  Transcript.prototype._scroll = function () {
    this.el.scrollTop = this.el.scrollHeight;
  };

  global.Transcript = Transcript;
})(window);
