"""Usage + cost tracking for NARA (Phase 6).

Every turn appends one JSON line to a usage log; ``nara stats`` summarizes it.
Cloud cost is only nonzero in ``cloud.backend: api`` mode — on a Pro/Max
subscription the CLI reports its own figure (usually $0, drawn from your plan).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .config import Config, load_config


@dataclass
class UsageRecord:
    ts: str
    route: str
    engine: str
    latency_ms: int
    cost_usd: float
    chars_in: int
    chars_out: int


def _is_cloud(route: str) -> bool:
    return route.startswith(("cloud", "dev"))


class UsageLog:
    """Append-only JSONL log of per-turn engine usage."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @classmethod
    def from_config(cls, cfg: Config | None = None) -> UsageLog:
        cfg = cfg or load_config()
        base = Path(cfg.get("logging.path", "~/.nara/logs")).expanduser()
        return cls(base / "usage.jsonl")

    def record(
        self, route: str, engine: str, latency_ms: int, cost_usd: float,
        chars_in: int, chars_out: int,
    ) -> UsageRecord:
        rec = UsageRecord(
            ts=datetime.now().astimezone().isoformat(timespec="seconds"),
            route=route or "?",
            engine=engine or "?",
            latency_ms=int(latency_ms),
            cost_usd=float(cost_usd or 0.0),
            chars_in=int(chars_in),
            chars_out=int(chars_out),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(rec)) + "\n")
        return rec

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def month_cost(self, year_month: str | None = None) -> float:
        year_month = year_month or datetime.now().strftime("%Y-%m")
        return round(
            sum(
                r.get("cost_usd", 0.0)
                for r in self.read()
                if str(r.get("ts", "")).startswith(year_month)
            ),
            4,
        )

    def summary(self) -> dict:
        rows = self.read()
        total = len(rows)
        local = sum(1 for r in rows if not _is_cloud(str(r.get("route", ""))))
        by_engine: dict[str, int] = {}
        for r in rows:
            key = r.get("engine", "?")
            by_engine[key] = by_engine.get(key, 0) + 1
        avg_latency = int(sum(r.get("latency_ms", 0) for r in rows) / total) if total else 0
        return {
            "total": total,
            "local": local,
            "cloud": total - local,
            "by_engine": by_engine,
            "total_cost": round(sum(r.get("cost_usd", 0.0) for r in rows), 4),
            "month_cost": self.month_cost(),
            "avg_latency_ms": avg_latency,
        }


def budget_status(cfg: Config, usage_log: UsageLog | None = None) -> dict:
    """Monthly cloud spend vs the configured cap."""
    usage_log = usage_log or UsageLog.from_config(cfg)
    cap = float(cfg.get("budget.monthly_cloud_usd", 0) or 0)
    warn_pct = float(cfg.get("budget.warn_at_percent", 80))
    spend = usage_log.month_cost()
    pct = (spend / cap * 100) if cap else 0.0
    return {
        "spend": spend,
        "cap": cap,
        "percent": round(pct, 1),
        "warn": cap > 0 and pct >= warn_pct,
        "over": cap > 0 and spend >= cap,
    }
