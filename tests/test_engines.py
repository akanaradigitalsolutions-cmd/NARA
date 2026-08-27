"""Phase 2 tests: engine response parsing (offline)."""
from __future__ import annotations

from types import SimpleNamespace

from core.engines import _extract_chat_text, _flatten


def test_extract_from_dict():
    assert _extract_chat_text({"message": {"content": "hello"}}) == "hello"


def test_extract_from_object():
    resp = SimpleNamespace(message=SimpleNamespace(content="hi", thinking=None))
    assert _extract_chat_text(resp) == "hi"


def test_reasoning_model_thinking_fallback():
    # content empty but a reasoning trace present -> use the trace.
    resp = {"message": {"content": "", "thinking": "the answer is 42"}}
    assert _extract_chat_text(resp) == "the answer is 42"


def test_empty_response_is_empty_string():
    assert _extract_chat_text({"message": {"content": ""}}) == ""
    assert _extract_chat_text({}) == ""


def test_strips_think_block_from_content():
    resp = {"message": {"content": "<think>let me check the notes</think>\n\n8am daily."}}
    assert _extract_chat_text(resp) == "8am daily."


def test_strips_stray_closing_think_tag():
    # Some servers drop the opening tag and leave a bare </think>.
    resp = {"message": {"content": "reasoning about it\n</think>\n\nThe answer is 42."}}
    assert _extract_chat_text(resp) == "The answer is 42."


def test_flatten_builds_prompt():
    prompt = _flatten("You are NARA.", [{"role": "user", "content": "hi"}])
    assert "You are NARA." in prompt
    assert "User: hi" in prompt
    assert prompt.rstrip().endswith("NARA:")
