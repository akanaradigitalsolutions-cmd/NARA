"""Model router — decide which engine handles a request (Phase 2).

    classify(user_msg, context) -> "local" | "cloud" | "dev"

Heuristics (config-driven thresholds), refined into a cloud-weighted policy in
Phase 6:

- a dev keyword (code/repo/build/deploy/debug/...) -> ``dev``
- a cloud keyword (analyze/plan/compare/...) or a lot of context -> ``cloud``
- everything else -> ``local``
"""
from __future__ import annotations

import re

from .config import Config

Route = str  # "local" | "cloud" | "dev"

_DEFAULT_DEV = ["code", "repo", "build", "deploy", "debug", "refactor", "test", "commit", "PR"]
_DEFAULT_CLOUD = ["analyze", "plan", "compare", "research", "synthesize", "strategy"]


def _has_keyword(text: str, keywords: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(k.lower())}\b", text) for k in keywords)


class Router:
    def __init__(
        self,
        dev_keywords: list[str] | None = None,
        cloud_keywords: list[str] | None = None,
        cloud_context_threshold_tokens: int = 800,
    ):
        self.dev_keywords = dev_keywords or list(_DEFAULT_DEV)
        self.cloud_keywords = cloud_keywords or list(_DEFAULT_CLOUD)
        self.cloud_context_threshold_tokens = cloud_context_threshold_tokens

    @classmethod
    def from_config(cls, cfg: Config) -> Router:
        return cls(
            dev_keywords=cfg.get("router.dev_keywords", _DEFAULT_DEV),
            cloud_keywords=cfg.get("router.cloud_keywords", _DEFAULT_CLOUD),
            cloud_context_threshold_tokens=cfg.get(
                "router.cloud_context_threshold_tokens", 800
            ),
        )

    def classify(self, user_msg: str, context: str = "") -> Route:
        text = user_msg.lower()
        if _has_keyword(text, self.dev_keywords):
            return "dev"
        approx_tokens = (len(user_msg) + len(context)) // 4
        if approx_tokens > self.cloud_context_threshold_tokens:
            return "cloud"
        if _has_keyword(text, self.cloud_keywords):
            return "cloud"
        return "local"


_default_router: Router | None = None


def classify(user_msg: str, context: str = "") -> Route:
    """Convenience wrapper using a router built from the default config."""
    global _default_router
    if _default_router is None:
        from .config import load_config

        _default_router = Router.from_config(load_config())
    return _default_router.classify(user_msg, context)
