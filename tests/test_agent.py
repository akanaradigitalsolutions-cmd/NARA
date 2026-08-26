"""Phase 2 tests: the Agent loop (routing, memory injection, history, remember).

Fully offline — engines are EchoEngine doubles and memory uses HashEmbedder.
"""
from __future__ import annotations

import pytest

from core.config import load_config
from core.engines import EchoEngine, EngineError, Reply
from core.memory import HashEmbedder, MemoryManager
from core.orchestrator import Agent
from core.router import Router


class FailEngine:
    def __init__(self, name: str = "fail"):
        self.name = name

    def generate(self, system, messages) -> Reply:
        raise EngineError("engine down")


@pytest.fixture
def memory(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    return MemoryManager(
        vault_path=vault,
        index_path=tmp_path / "index.lancedb",
        embedder=HashEmbedder(dim=256),
    )


def _agent(memory, local=None, cloud=None):
    return Agent(
        load_config(),
        memory,
        Router(),
        local or EchoEngine("echo-local"),
        cloud or EchoEngine("echo-cloud"),
        history_turns=6,
        memory_k=6,
    )


def test_plain_chat_uses_local_engine(memory):
    local, cloud = EchoEngine("echo-local"), EchoEngine("echo-cloud")
    agent = _agent(memory, local, cloud)
    reply = agent.run("what's on my plate today?")
    assert local.calls == 1 and cloud.calls == 0
    assert reply.route == "local"


def test_cloud_keyword_uses_cloud_engine(memory):
    local, cloud = EchoEngine("echo-local"), EchoEngine("echo-cloud")
    agent = _agent(memory, local, cloud)
    reply = agent.run("analyze the spa revenue trend")
    assert cloud.calls == 1 and local.calls == 0
    assert reply.route == "cloud"


def test_memory_is_injected_into_system_prompt(memory):
    memory.remember("Relaxha aromatherapy massage is 150k IDR")
    local = EchoEngine("echo-local")
    agent = _agent(memory, local=local)
    agent.run("how much is a massage?")
    assert "150k" in (local.last_system or "")


def test_history_carries_across_turns(memory):
    local = EchoEngine("echo-local")
    agent = _agent(memory, local=local)
    agent.run("hi")
    agent.run("again")
    assert len(agent.history) == 4
    # Second turn's message window includes the first exchange.
    assert local.last_messages[0]["content"] == "hi"
    assert local.last_messages[-1]["content"] == "again"


def test_explicit_remember_saves_and_skips_engines(memory):
    local, cloud = EchoEngine("echo-local"), EchoEngine("echo-cloud")
    agent = _agent(memory, local, cloud)
    reply = agent.run("remember that the villa gate code is 4821")
    assert reply.engine == "memory"
    assert local.calls == 0 and cloud.calls == 0
    notes = list((memory.vault_path / "NARA" / "Memory").glob("*.md"))
    assert notes and "4821" in notes[0].read_text(encoding="utf-8")


def test_engine_fallback_when_primary_fails(memory):
    # Local route, but the local engine is down -> fall back to cloud.
    agent = _agent(memory, local=FailEngine("fail-local"), cloud=EchoEngine("echo-cloud"))
    reply = agent.run("hello there")
    assert reply.engine == "echo-cloud"
    assert "unavailable" in reply.text
