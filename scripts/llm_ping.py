"""One cheap API call through the budget guard, to check key, model and cost accounting.

    python scripts/llm_ping.py
"""

from __future__ import annotations

import sys

from desks.config import LLMConfig, load_dotenv
from desks.llm import make_client


def main() -> int:
    load_dotenv()
    cfg = LLMConfig()
    client = make_client(cfg)
    r = client.complete(
        "Reply with JSON only.",
        [{"role": "user", "content": 'Return {"ok": true, "n": 7}.'}],
        max_tokens=50,
    )
    print(f"model={r.model} stop={r.stop_reason} in={r.input_tokens} out={r.output_tokens} cost=${r.cost:.6f} latency={r.latency_s:.2f}s")
    print(f"text={r.text!r}")
    print(f"ledger total=${client.guard.spent():.6f} (budget ${client.guard.budget:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
