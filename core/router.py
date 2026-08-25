"""Model router — decide which engine handles a request.

Implemented in **Phase 2 — The Core Agent** and upgraded to a cloud-weighted
policy in **Phase 6**. Will expose:

    classify(user_msg, context) -> "local" | "cloud" | "dev"

Starting with keyword + length heuristics (config-driven thresholds), then
refined with a tiny local classifier trained on NARA's own route logs.
"""
from __future__ import annotations

Route = str  # one of: "local" | "cloud" | "dev"


def classify(user_msg: str, context: str = "") -> Route:
    raise NotImplementedError("Phase 2: implement local/cloud/dev routing")
