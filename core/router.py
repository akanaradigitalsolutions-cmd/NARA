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
_DEFAULT_SENSITIVE = ["password", "secret", "private", "diary", "medical", "bank", "salary"]
_DEFAULT_UNCERTAIN = [
    "i'm not sure", "i am not sure", "i don't know", "i do not know", "not certain",
    "cannot help", "can't help", "unable to", "no information", "i cannot", "i can't",
]


def _has_keyword(text: str, keywords: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(k.lower())}\b", text) for k in keywords)


class Router:
    def __init__(
        self,
        dev_keywords: list[str] | None = None,
        cloud_keywords: list[str] | None = None,
        cloud_context_threshold_tokens: int = 800,
        sensitive_keywords: list[str] | None = None,
        low_confidence_markers: list[str] | None = None,
    ):
        self.dev_keywords = dev_keywords or list(_DEFAULT_DEV)
        self.cloud_keywords = cloud_keywords or list(_DEFAULT_CLOUD)
        self.cloud_context_threshold_tokens = cloud_context_threshold_tokens
        self.sensitive_keywords = sensitive_keywords or list(_DEFAULT_SENSITIVE)
        self.low_confidence_markers = low_confidence_markers or list(_DEFAULT_UNCERTAIN)

    @classmethod
    def from_config(cls, cfg: Config) -> Router:
        return cls(
            dev_keywords=cfg.get("router.dev_keywords", _DEFAULT_DEV),
            cloud_keywords=cfg.get("router.cloud_keywords", _DEFAULT_CLOUD),
            cloud_context_threshold_tokens=cfg.get(
                "router.cloud_context_threshold_tokens", 800
            ),
            sensitive_keywords=cfg.get("privacy.sensitive_keywords", _DEFAULT_SENSITIVE),
            low_confidence_markers=cfg.get("router.low_confidence_markers", _DEFAULT_UNCERTAIN),
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

    def is_private(self, user_msg: str) -> bool:
        """True if the message looks sensitive — answer locally, never cloud."""
        return _has_keyword(user_msg.lower(), self.sensitive_keywords)

    def low_confidence(self, text: str) -> bool:
        """True if a local reply looks unsure enough to escalate to the cloud."""
        stripped = (text or "").strip().lower()
        if len(stripped) < 3:
            return True
        return any(marker in stripped for marker in self.low_confidence_markers)


_default_router: Router | None = None


def classify(user_msg: str, context: str = "") -> Route:
    """Convenience wrapper using a router built from the default config."""
    global _default_router
    if _default_router is None:
        from .config import load_config

        _default_router = Router.from_config(load_config())
    return _default_router.classify(user_msg, context)
