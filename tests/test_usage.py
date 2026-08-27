"""Phase 6 tests: usage logging + budget status."""
from __future__ import annotations

from core.usage import UsageLog, budget_status


class FakeCfg:
    def __init__(self, data: dict):
        self.data = data

    def get(self, dotted: str, default=None):
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def test_record_and_summary(tmp_path):
    log = UsageLog(tmp_path / "usage.jsonl")
    log.record("local", "ollama:qwen3:4b", 120, 0.0, 10, 20)
    log.record("cloud", "claude-cli", 900, 0.0, 50, 200)
    log.record("cloud+esc", "claude-cli", 800, 0.25, 30, 150)

    s = log.summary()
    assert s["total"] == 3
    assert s["local"] == 1
    assert s["cloud"] == 2
    assert s["by_engine"]["claude-cli"] == 2
    assert s["total_cost"] == 0.25
    assert s["avg_latency_ms"] > 0


def test_summary_of_missing_log_is_empty(tmp_path):
    assert UsageLog(tmp_path / "none.jsonl").summary()["total"] == 0


def test_budget_status_under_then_over(tmp_path):
    log = UsageLog(tmp_path / "u.jsonl")
    cfg = FakeCfg({"budget": {"monthly_cloud_usd": 50, "warn_at_percent": 80}})

    log.record("cloud", "anthropic:x", 100, 30.0, 1, 1)  # 60% of cap
    under = budget_status(cfg, log)
    assert under["cap"] == 50
    assert under["spend"] == 30.0
    assert under["over"] is False
    assert under["warn"] is False

    log.record("cloud", "anthropic:x", 100, 25.0, 1, 1)  # now 55 > 50
    over = budget_status(cfg, log)
    assert over["over"] is True


def test_no_cap_means_never_over(tmp_path):
    log = UsageLog(tmp_path / "u.jsonl")
    log.record("cloud", "x", 1, 999.0, 1, 1)
    b = budget_status(FakeCfg({"budget": {"monthly_cloud_usd": 0}}), log)
    assert b["over"] is False
    assert b["warn"] is False
