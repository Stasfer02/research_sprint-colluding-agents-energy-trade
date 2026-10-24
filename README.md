# Colluding Desks

**How do reasoning and stated regulatory rules influence potentially manipulative behaviour of LLM agents in a simulated electricity balancing market?**

Apart Research — AI Collusion Research Sprint (23–25 Oct 2026). This is an exploratory simulation study with five runs per condition.

## The simulation

Three firms each run two LLM agents (DeepSeek-V4-Flash):
- a **trading desk**, which chooses a deliberate deviation from its forecast position and is settled at the imbalance price;
- a **balancing desk**, which bids balancing energy to the grid operator.

The last activated bid sets the imbalance price, so the price links a firm's two desks. Both desks maximise the firm's total profit, but an information barrier separates them, and their only channel is a public board that the regulator can read. Each run lasts 30 periods. A competitive benchmark with the same random shocks gives every run an exact counterfactual.

Market rules: `src/desks/market.py`. Period loop: `src/desks/simulation.py`. Prompts: `src/desks/prompts/`.

## Conditions

| | Condition | Config |
|---|---|---|
| EXP7 | baseline, reasoning off | `configs/experiments/exp7_deepseek_desks.yaml` |
| EXP8 | reasoning effort "high" | `configs/experiments/exp8_deepseek_desks_reasoning.yaml` |
| EXP9 | EXP8 + REMIT compliance text (not enforced) | `configs/experiments/exp9_deepseek_desks_rules.yaml` |

Each condition runs seeds 0–4. A given seed produces identical market shocks in every condition. Pre-registrations are in [docs/experiments/](docs/experiments/README.md).

## Documents

- Report draft: [docs/paper/report.md](docs/paper/report.md), with the methods in [docs/paper/methods.md](docs/paper/methods.md)
- Results table and figure: [results/core/comparison.md](results/core/comparison.md)
- Related work: [docs/related-work.md](docs/related-work.md)
- What was simplified: [docs/simplification.md](docs/simplification.md). Earlier experiments (EXP0–EXP6), their results and the older docs are no longer in the current tree. They remain in the git history at commit `2ea0394`.

## Reproducing

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/pytest -q                      # includes a replay of every committed EXP7–9 period; no API calls
.venv/bin/python scripts/analyze.py      # results/core/comparison.md, per_run.csv, figures/behaviour.png
.venv/bin/python scripts/show_transcript.py results/exp8_deepseek_desks_reasoning/runs/baseline/seed_0 --periods 1-3
```

The analysis reads only committed files. Re-running the conditions calls the API; it needs keys in `.env` (see `.env.example`):

```bash
.venv/bin/python scripts/run_grid.py configs/experiments/exp8_deepseek_desks_reasoning.yaml --workers 5
.venv/bin/python scripts/export_results.py runs/exp8_deepseek_desks_reasoning results/exp8_deepseek_desks_reasoning
```

- **Cost.** EXP7 cost $0.19 and EXP8 $0.96 for five runs.
- **Budget guard.** Every call goes through a spend ledger (`runs/ledger*.json`) with a hard cap.
- **Not bit-identical.** LLM sampling can differ between runs even with logged seeds. For that reason every prompt, raw output and reasoning text is committed under `results/`.
- **Provenance.** Each run's `provenance.json` records the git commit and a hash of the prompt templates.

## Credits and disclosures

- **New work.** All code was written during the sprint, with Claude Code. No pre-existing code is included.
- **Design inspiration:** Agrawal et al. (2025), *Evaluating LLM Agent Collusion in Double Auctions* ([arXiv:2507.01413](https://arxiv.org/abs/2507.01413), [code](https://github.com/andyjliu/llm-agent-collusion)). We reuse ideas, not code.
- **Dual use.** The market is deliberately stylised: one product, synthetic noise, and no real companies or data.
