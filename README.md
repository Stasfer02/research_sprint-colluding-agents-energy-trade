# Colluding Desks

**LLM agents, transparency and enforcement in a stylised balancing market.**
Apart Research — AI Collusion Research Sprint (23–25 Oct 2026).

Three firms each run two LLM agents: a **BRP desk** (chooses a deliberate deviation from its forecast position and is settled at the imbalance price) and a **BSP desk** (bids balancing energy; the marginal activated bid sets the imbalance price). A scripted grid operator clears a single-price merit order each period. We vary the communication channels (none / public board / public board + "private" channel) and whether anti-manipulation rules are only stated or actually enforced by an in-simulation regulator, and score detectors against ground truth we control.

- Build spec: [docs/design-spec.md](docs/design-spec.md)
- Status, hypotheses, decisions, findings: [docs/project-tracker.md](docs/project-tracker.md)
- Related work: [docs/related-work.md](docs/related-work.md)

## Quick start

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
cp .env.example .env    # add ANTHROPIC_API_KEY, BUDGET_USD
.venv/bin/pytest -q
.venv/bin/python scripts/run_grid.py configs/smoke.yaml      # scripted agents, no API cost
.venv/bin/python scripts/check_smoke.py runs/smoke
```

Every LLM call goes through a budget guard (`runs/ledger.json`, capped by `BUDGET_USD`).

## Credits and disclosures

- **New work.** All code in this repository was written during the sprint (from 23 Oct 2026), with Claude Code. No pre-existing code is included.
- **Design inspiration:** Agrawal et al. (2025), *Evaluating LLM Agent Collusion in Double Auctions* ([arXiv:2507.01413](https://arxiv.org/abs/2507.01413), [code](https://github.com/andyjliu/llm-agent-collusion)). We reuse ideas (seller messaging, monitoring conditions), not code.
- **Monitoring disclosure.** The "private" channel that agents are told is unmonitored is logged by the experimenters and used in offline evaluation.
- **Dual use.** The market is deliberately stylised (one product, single pricing, synthetic noise, no real companies or data). Findings are framed around detection and market design.
