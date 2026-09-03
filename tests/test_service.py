"""Phase 5 tests: the local HTTP service (with an injected fake agent)."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from core.config import load_config  # noqa: E402
from core.engines import Reply  # noqa: E402
from core.service import create_app  # noqa: E402


class FakeAgent:
    def run(self, message: str) -> Reply:
        return Reply(text=f"echo: {message}", engine="echo", route="local")


def _client() -> TestClient:
    return TestClient(create_app(load_config(), agent=FakeAgent()))


def test_status_endpoint():
    resp = _client().get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["name"]


def test_chat_endpoint():
    resp = _client().post("/chat", json={"message": "hi there"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "echo: hi there"
    assert body["route"] == "local"


def test_chat_requires_message():
    resp = _client().post("/chat", json={})
    assert resp.status_code == 422  # validation error


def test_ui_is_served():
    resp = _client().get("/ui/")
    assert resp.status_code == 200
    assert "NARA" in resp.text


def test_root_redirects_to_ui():
    resp = _client().get("/")  # TestClient follows the redirect
    assert resp.status_code == 200
    assert "Command Center" in resp.text


def test_ws_streams_state_and_reply():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({"message": "hello"})
        events = []
        for _ in range(12):
            evt = ws.receive_json()
            events.append(evt)
            if evt.get("type") == "state" and evt.get("state") == "idle":
                break
    types = [e["type"] for e in events]
    assert "state" in types
    turn = next(e for e in events if e["type"] == "turn")
    assert turn["text"] == "echo: hello"  # from FakeAgent
    assert turn["route"] == "local"
    assert "latency_ms" in turn
    # thinking must precede speaking must precede idle
    states = [e["state"] for e in events if e["type"] == "state"]
    assert states.index("thinking") < states.index("speaking") < states.index("idle")
