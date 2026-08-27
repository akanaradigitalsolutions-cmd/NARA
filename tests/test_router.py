"""Phase 2 tests: model routing heuristics."""
from __future__ import annotations

from core.router import Router


def test_dev_keywords_route_to_dev():
    r = Router()
    assert r.classify("Can you debug the booking service?") == "dev"
    assert r.classify("deploy the laundry app") == "dev"
    assert r.classify("open a PR for that") == "dev"


def test_cloud_keywords_route_to_cloud():
    r = Router()
    assert r.classify("analyze last month's spa revenue") == "cloud"
    assert r.classify("compare these two suppliers") == "cloud"


def test_plain_chat_routes_local():
    r = Router()
    assert r.classify("what's on my plate today?") == "local"
    assert r.classify("say hello") == "local"


def test_long_context_routes_cloud():
    r = Router(cloud_context_threshold_tokens=50)
    long_context = "word " * 400  # ~500 chars -> ~125 tokens > 50
    assert r.classify("summarize this", context=long_context) == "cloud"


def test_keyword_matching_is_word_bounded():
    r = Router()
    # "contest" contains "test" but must not trigger the dev route.
    assert r.classify("who won the contest?") == "local"


def test_is_private_flags_sensitive():
    r = Router()
    assert r.is_private("what is my bank password") is True
    assert r.is_private("remind me my salary figure") is True
    assert r.is_private("what's the weather today") is False


def test_low_confidence_detection():
    r = Router()
    assert r.low_confidence("I'm not sure about that.") is True
    assert r.low_confidence("") is True
    assert r.low_confidence("Pickup is 8am daily.") is False
