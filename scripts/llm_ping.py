"""One cheap call per model through the budget guards: checks key, routing, pinned provider, seed and reasoning.

    python scripts/llm_ping.py                              # default model (claude-haiku-5-5)
    python scripts/llm_ping.py qwen/qwen3.8-flash ...       # OpenRouter models from configs/models_openrouter.yaml
"""

from __future__ import annotations

import sys

from desks.config import LLMConfig, load_dotenv
from desks.llm import make_client


def main() -> int:
    load_dotenv()
    models = sys.argv[1:] or [LLMConfig().model]
    cfg = LLMConfig(temperature=0.7)
    client = make_client(cfg, firm_models={str(i): m for i, m in enumerate(models)})
    status = 0
    for m in models:
        try:
            r = client.complete("Reply with JSON only.", [{"role": "user", "content": 'Return {"ok": true, "n": 7}.'}],
                                model=m, max_tokens=120, seed=42)
        except Exception as exc:  # noqa: BLE001 - report and continue with the next model
            print(f"FAIL {m}: {type(exc).__name__}: {str(exc)[:300]}")
            status = 1
            continue
        meta = r.meta
        print(f"OK   {m}: stop={r.stop_reason} in={r.input_tokens} out={r.output_tokens} cost=${r.cost:.6f} "
              f"{r.latency_s:.1f}s provider={meta.get('provider')} (pinned {meta.get('provider_pinned')}) "
              f"seed={meta.get('seed_sent')} temp={meta.get('temperature_sent')} reasoning_tokens={meta.get('reasoning_tokens')}")
        print(f"     text={r.text[:120]!r}")
    for name, c in client.routes.items():
        print(f"ledger {name}: ${c.guard.spent():.4f} of ${c.guard.budget:.2f}")
    return status


if __name__ == "__main__":
    sys.exit(main())
