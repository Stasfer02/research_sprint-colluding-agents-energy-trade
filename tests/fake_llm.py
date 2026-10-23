"""Fake LLM responders for tests (no API calls)."""

from __future__ import annotations

import json
import re


def role_of(system: str) -> str:
    first = system.splitlines()[0]
    if "trading desk" in first:
        return "brp"
    if "balancing desk" in first:
        return "bsp"
    if "firm desk" in first:
        return "integrated"
    return "judge"


def valid_responder(system: str, messages: list[dict], model: str) -> str:
    role = role_of(system)
    if role == "judge":
        return json.dumps({"score": 1, "reason": "nothing notable"})
    t = int(re.search(r"Period (\d+) of", messages[0]["content"]).group(1))
    out = {"reflection": "ok", "plan": "hold", "public_post": f"post t={t}", "private_message": None, "notes": f"notes t={t}"}
    if role in ("brp", "integrated"):
        out["deviation_mw"] = 5.0 if t % 2 else -5.0
    if role in ("bsp", "integrated"):
        out["up_bid"] = 90
        out["down_bid"] = 40
    return "Here is my answer:\n" + json.dumps(out)
