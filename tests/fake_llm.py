"""Fake LLM responder for tests (no API calls)."""

from __future__ import annotations

import json
import re


def role_of(system: str) -> str:
    return "brp" if "trading desk" in system.splitlines()[0] else "bsp"


def valid_responder(system: str, messages: list[dict], model: str) -> str:
    """A well-formed desk reply: alternating deviations for trading desks, fixed bids for balancing desks."""
    t = int(re.search(r"Period (\d+) of", messages[0]["content"]).group(1))
    out = {"reflection": "ok", "plan": "hold", "public_post": f"post t={t}", "private_message": None, "notes": f"notes t={t}"}
    if role_of(system) == "brp":
        out["deviation_mw"] = 5.0 if t % 2 else -5.0
    else:
        out["up_bid"], out["down_bid"] = 90, 40
    return "Here is my answer:\n" + json.dumps(out)
