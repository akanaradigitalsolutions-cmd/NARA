"""Local HTTP service for NARA (Phase 5).

A small FastAPI app so any UI (menu-bar, a HUD window, scripts) can talk to the
same NARA core over HTTP instead of embedding it. fastapi/uvicorn are imported
lazily, so this module loads without the ``[service]`` extra.

Endpoints:
    GET  /status   -> basic health + config
    POST /chat     -> {"message": "..."} -> {"reply", "engine", "route"}
    POST /reindex  -> rebuild the vault index

Run:  nara serve   (or: python -m core.service)
"""

from .config import REPO_ROOT, Config, load_config


def create_app(cfg: Config | None = None, agent=None):
    """Build the FastAPI app. ``agent`` may be injected (tests); else built lazily."""
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from pydantic import BaseModel

    cfg = cfg or load_config()
    state = {"agent": agent}

    class ChatIn(BaseModel):
        message: str

    def get_agent():
        if state["agent"] is None:
            from .orchestrator import Agent

            state["agent"] = Agent.from_config(cfg)
        return state["agent"]

    app = FastAPI(title="NARA", version="0.1.0")

    @app.get("/status")
    def status():
        return {
            "name": cfg.get("persona.name", "NARA"),
            "ok": True,
            "cloud_backend": cfg.get("cloud.backend", "cli"),
            "vault": str(cfg.get("vault.path", "")),
        }

    @app.post("/chat")
    def chat(body: ChatIn):
        reply = get_agent().run(body.message)
        return {"reply": reply.text, "engine": reply.engine, "route": reply.route}

    @app.post("/reindex")
    def reindex():
        from .memory import MemoryManager

        stats = MemoryManager.from_config(cfg).reindex()
        return {"stats": str(stats)}

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        """Drive the HUD: receive a user message, stream back state + reply.

        Emits state transitions (thinking → speaking → idle) and a `turn` event
        carrying NARA's reply plus live telemetry (engine, route, cost, latency).
        """
        import time as _time

        from starlette.concurrency import run_in_threadpool

        await sock.accept()
        try:
            while True:
                data = await sock.receive_json()
                message = str((data or {}).get("message", "")).strip()
                if not message:
                    continue
                await sock.send_json({"type": "state", "state": "thinking"})
                t0 = _time.perf_counter()
                reply = await run_in_threadpool(get_agent().run, message)
                latency_ms = int((_time.perf_counter() - t0) * 1000)
                await sock.send_json({"type": "state", "state": "speaking"})
                await sock.send_json(
                    {
                        "type": "turn",
                        "who": "nara",
                        "text": reply.text,
                        "engine": reply.engine,
                        "route": reply.route,
                        "cost": reply.cost_usd or 0.0,
                        "latency_ms": latency_ms,
                    }
                )
                await sock.send_json({"type": "state", "state": "idle"})
        except WebSocketDisconnect:
            return

    # Serve the JARVIS HUD (web/) at /ui, and redirect the bare root to it.
    web_dir = REPO_ROOT / "web"
    if web_dir.is_dir():
        from fastapi.responses import RedirectResponse
        from fastapi.staticfiles import StaticFiles

        @app.get("/")
        def root():
            return RedirectResponse(url="/ui/")

        app.mount("/ui", StaticFiles(directory=str(web_dir), html=True), name="ui")

    return app


def main() -> None:
    import uvicorn

    cfg = load_config()
    host = cfg.get("service.host", "127.0.0.1")
    port = int(cfg.get("service.port", 8765))
    print(f"NARA service on http://{host}:{port}  (Ctrl-C to stop)")
    uvicorn.run(create_app(cfg), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
