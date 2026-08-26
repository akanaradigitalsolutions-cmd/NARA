"""Reasoning engines for NARA (Phase 2).

An ``Engine`` turns a system prompt + conversation into a reply. Three backends:

- ``OllamaEngine``    — local models (default for routine chat)
- ``ClaudeCLIEngine`` — cloud Claude via the local `claude` CLI on a Pro/Max
  subscription (no API key); this is the default cloud path
- ``AnthropicEngine`` — cloud Claude via the Anthropic API (used when
  ``cloud.backend: api``)

``EchoEngine`` is a deterministic test double. All heavy imports are lazy so the
module loads without ollama/anthropic installed.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Protocol

Message = dict  # {"role": "user" | "assistant", "content": str}


class EngineError(RuntimeError):
    """Raised when an engine cannot produce a reply."""


@dataclass
class Reply:
    text: str
    engine: str
    cost_usd: float | None = None
    route: str | None = None  # set by the Agent: "local" | "cloud" | "dev" | ...


class Engine(Protocol):
    name: str

    def generate(self, system: str, messages: list[Message]) -> Reply: ...


def _flatten(system: str, messages: list[Message]) -> str:
    """Render a system prompt + turns into a single prompt for a one-shot CLI."""
    parts = [system.strip(), ""]
    for m in messages:
        speaker = "User" if m.get("role") == "user" else "NARA"
        parts.append(f"{speaker}: {m.get('content', '')}")
    parts.append("NARA:")
    return "\n".join(parts)


def _ollama_chat(client, model: str, payload: list[Message]):
    """Call ollama.chat, disabling reasoning when the client/server supports it.

    ``think=False`` gives a direct answer from reasoning models (qwen3, ...) and
    is much faster; older clients/servers reject the kwarg, so retry plainly.
    """
    try:
        return client.chat(model=model, messages=payload, think=False)
    except Exception:  # noqa: BLE001 - unsupported `think`; retry without it
        return client.chat(model=model, messages=payload)


def _extract_chat_text(resp) -> str:
    """Pull the reply text from an ollama chat response (dict or object).

    Reasoning models may put the answer in ``content`` and the chain-of-thought
    in ``thinking``; if ``content`` is empty, fall back to ``thinking``.
    """
    message = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", None)
    if message is None:
        return ""
    if isinstance(message, dict):
        content, thinking = message.get("content"), message.get("thinking")
    else:
        content, thinking = getattr(message, "content", None), getattr(message, "thinking", None)
    text = (content or "").strip()
    if not text and thinking:
        text = thinking.strip()
    return text


class OllamaEngine:
    """Local chat via an Ollama model."""

    def __init__(self, model: str, host: str | None = None):
        self.model = model
        self.host = host
        self.name = f"ollama:{model}"

    def generate(self, system: str, messages: list[Message]) -> Reply:
        import ollama

        client = ollama.Client(host=self.host) if self.host else ollama
        payload = [{"role": "system", "content": system}, *messages]
        try:
            resp = _ollama_chat(client, self.model, payload)
        except Exception as exc:  # ollama raises several connection/response types
            raise EngineError(
                f"Ollama call failed ({exc}). Is Ollama running and is "
                f"'{self.model}' pulled? Try: ollama pull {self.model}"
            ) from exc
        text = _extract_chat_text(resp)
        if not text:
            raise EngineError(f"{self.model} returned an empty response")
        return Reply(text=text, engine=self.name)


class ClaudeCLIEngine:
    """Cloud reasoning via the local `claude` CLI (Pro/Max subscription, no key)."""

    def __init__(self, binary: str = "claude", timeout: int = 120, extra_args=None):
        self.binary = binary
        self.timeout = timeout
        self.extra_args = list(extra_args or [])
        self.name = "claude-cli"

    def generate(self, system: str, messages: list[Message]) -> Reply:
        prompt = _flatten(system, messages)
        cmd = [self.binary, "-p", prompt, "--output-format", "json", *self.extra_args]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout, check=False
            )
        except FileNotFoundError as exc:
            raise EngineError(
                "`claude` CLI not found. Install Claude Code and run `claude login`."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise EngineError(f"claude timed out after {self.timeout}s") from exc
        if proc.returncode != 0:
            raise EngineError(
                f"claude exited {proc.returncode}: {proc.stderr.strip()[:300]} "
                "(are you logged in? run `claude login`)"
            )
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return Reply(text=proc.stdout.strip(), engine=self.name)
        return Reply(
            text=(data.get("result") or "").strip(),
            engine=self.name,
            cost_usd=data.get("total_cost_usd"),
        )


class AnthropicEngine:
    """Cloud reasoning via the Anthropic API (used when cloud.backend == 'api')."""

    def __init__(self, model: str, max_tokens: int = 4096):
        self.model = model
        self.max_tokens = max_tokens
        self.name = f"anthropic:{model}"
        self._client = None

    def _client_(self):
        import anthropic

        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def generate(self, system: str, messages: list[Message]) -> Reply:
        import anthropic

        try:
            resp = self._client_().messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=list(messages),
            )
        except anthropic.APIError as exc:
            raise EngineError(f"Anthropic API error: {exc}") from exc
        text = next((b.text for b in resp.content if b.type == "text"), "")
        cost = None
        usage = getattr(resp, "usage", None)
        if usage is not None:
            cost = _estimate_cost(self.model, usage)
        return Reply(text=text.strip(), engine=self.name, cost_usd=cost)


class EchoEngine:
    """Deterministic engine for tests; records what it was asked to generate."""

    def __init__(self, name: str = "echo", reply: str | None = None):
        self.name = name
        self._reply = reply
        self.last_system: str | None = None
        self.last_messages: list[Message] | None = None
        self.calls = 0

    def generate(self, system: str, messages: list[Message]) -> Reply:
        self.calls += 1
        self.last_system = system
        self.last_messages = list(messages)
        text = self._reply if self._reply is not None else messages[-1]["content"]
        return Reply(text=text, engine=self.name)


# Rough input/output $/1M for cost display in api mode (see config model tiers).
_PRICES = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def _estimate_cost(model: str, usage) -> float | None:
    price = _PRICES.get(model)
    if not price:
        return None
    in_tok = getattr(usage, "input_tokens", 0) or 0
    out_tok = getattr(usage, "output_tokens", 0) or 0
    return round(in_tok / 1e6 * price[0] + out_tok / 1e6 * price[1], 6)


def build_cloud_engine(cfg) -> Engine:
    """Pick the cloud engine from config (`cloud.backend`)."""
    backend = str(cfg.get("cloud.backend", "cli")).lower()
    if backend == "api":
        return AnthropicEngine(
            cfg.get("models.cloud_model", "claude-sonnet-5"),
            max_tokens=cfg.get("cloud.max_tokens", 4096),
        )
    return ClaudeCLIEngine(timeout=cfg.get("cloud.timeout_seconds", 120))


def build_local_engine(cfg) -> Engine:
    """Local chat engine (small resident model by default)."""
    model = cfg.get("agent.local_model") or cfg.get("models.voice_model") or "qwen3:4b"
    return OllamaEngine(model)
