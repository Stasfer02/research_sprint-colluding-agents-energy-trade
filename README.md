# Colluding Desks

**How do reasoning and stated regulatory rules influence potentially manipulative behaviour of LLM agents in a simulated electricity balancing market?**

Apart Research — AI Collusion Research Sprint (23–25 Oct 2026). This is an exploratory simulation study with five runs per condition.

## The simulation

Three firms each run two LLM agents (DeepSeek-V4-Flash):
- a **trading desk**, which chooses a deliberate deviation from its forecast position and is settled at the imbalance price;
- a **balancing desk**, which bids balancing energy to the grid operator.

The last activated bid sets the imbalance price, so the price links a firm's two desks. Both desks maximise the firm's total profit. An information barrier separates them, and their only channel is a public board that the regulator can read. Each run lasts 30 periods.

**The result is the agents' reasoning.** With reasoning on, every decision comes with a reasoning trace. We code these traces for coordination intent with the firm's own other desk and with other firms, and compare EXP2 (reasoning) with EXP3 (reasoning plus stated rules). Public requests and next-period responses are measured alongside. The protocol is in [docs/experiments/trace_analysis.md](docs/experiments/trace_analysis.md).

> **The simulation was generated with Claude, and we have not yet thoroughly reviewed its soundness.** The market, the agents' prompts and the analysis code were written with Claude Code during the sprint.
>
> **What the tests show:** the code is internally consistent and reproducible. They check clearing and settlement against hand-computed cases, and replay every committed run exactly.
>
> **What they don't show:** that the market is a sound or faithful model of a real balancing market. We haven't checked that systematically.
>
> This is a limitation, but checking it was not the goal of this project. We were mainly interested in the agents' behaviour: how they reason about, communicate and act on the incentive that links a firm's two desks. Treat the market as a stylised setting for studying that behaviour, not as a validated market model.

## Conditions

| | Condition | Config and results (working name) |
|---|---|---|
| EXP1 | baseline, reasoning off | `configs/experiments/exp7_deepseek_desks.yaml` (EXP7) |
| EXP2 | reasoning effort "high" | `configs/experiments/exp8_deepseek_desks_reasoning.yaml` (EXP8) |
| EXP3 | EXP2 + REMIT compliance text (not enforced) | `configs/experiments/exp9_deepseek_desks_rules.yaml` (EXP9) |

The report calls the conditions EXP1–EXP3. Folders, configs and the git history use the working names EXP7–EXP9 (EXP1 = EXP7, EXP2 = EXP8, EXP3 = EXP9).

Each condition runs seeds 0–4. A given seed produces identical market shocks in every condition. EXP1 has no reasoning traces; it is kept as the run without reasoning.

## Repository

| Path | Contents |
|---|---|
| `src/desks/` | The simulation:<br>• `market.py`: clearing and settlement<br>• `simulation.py`: period loop, what each desk sees<br>• `agents.py` and `prompts/`: LLM desks<br>• `llm.py`: API clients and budget guard<br>• `config.py`, `runner.py` |
| `configs/` | The three experiment configs (plus the EXP3 re-run of seeds 0, 2, 4) and the pinned OpenRouter model |
| `scripts/` | Running and analysis:<br>• `run_grid.py`, `export_results.py`: run and export<br>• `code_traces.py`: Haiku codes the reasoning traces<br>• `trace_evidence.py`: public requests, responses and the summary table<br>• `plot_trace_timeline.py`: the intent-over-time figure<br>• `compare_validation.py`: hand labels against the coder<br>• `show_transcript.py`: read a run |
| `results/` | Every committed run (prompts, raw outputs, reasoning text, market records) and `trace_analysis/` (codes, summary table, figure, validation) |
| `docs/` | `formal-model.md` (the simulation in equations), `experiments/trace_analysis.md` (the reasoning-trace protocol and judge validation) |
| `tests/` | Tests without API calls, including a replay of all committed runs |

## Reproducing

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/pytest -q                       # re-runs all 15 committed runs end to end against their logs; no API calls
.venv/bin/python scripts/trace_evidence.py      # results/trace_analysis/evidence.md (uses the committed trace codes)
.venv/bin/python scripts/plot_trace_timeline.py  # results/trace_analysis/figures/intent_over_time.png
.venv/bin/python scripts/show_transcript.py results/exp8_deepseek_desks_reasoning/runs/baseline/seed_1 --periods 18 --desk C:bsp --reasoning
```

The analysis reads only committed files. Re-running a condition or the trace coder calls an API, so it needs keys in `.env` (see `.env.example`):

```bash
.venv/bin/python scripts/run_grid.py configs/experiments/exp8_deepseek_desks_reasoning.yaml --workers 5
.venv/bin/python scripts/export_results.py runs/exp8_deepseek_desks_reasoning results/exp8_deepseek_desks_reasoning
.venv/bin/python scripts/code_traces.py --max-usd 5    # Haiku codes every EXP2/EXP3 reasoning trace
```

- **Cost.** Five runs cost $0.19 (EXP1), $0.96 (EXP2) and $0.89 (EXP3), including the end-of-run judge those runs had. Coding all EXP2 and EXP3 traces cost $3.44.
- **Budget guard.** Every call goes through a spend ledger (`runs/ledger*.json`) with a hard cap.
- **Not bit-identical.** LLM sampling can differ between runs even with logged seeds. For that reason every prompt, raw output and reasoning text is committed under `results/`.
- **Provenance.** Each run's `provenance.json` records the git commit and a hash of the prompt templates.

## Known limits

- **Few runs.** Five runs per condition, so all comparisons are descriptive.
- **Stylised market.** One 40 MW block per firm, synthetic shocks, a single price. The intent the agents express reflects how they reason about the incentive, not a strategy shown to be profitable.
- **Automated coding.** Coordination intent is coded by Haiku. Checked against hand labels, within-firm intent matches well: weighted kappa 0.85, and score 3 is precise. Score ≥ 2 is over-counted, and the cross-firm scores were not supported. Intent in the reasoning is reported intent, not proof of what drove a decision.
- **Conditions differ in more than one parameter.** EXP2 also raises the output limit and timeout. EXP3 also shows a fine column (always 0). EXP3 seeds 0, 2 and 4 were re-run with a higher retry limit.
- **Rules stated, not enforced.** EXP3's text bans "collusion with other firms" and manipulation, but does not name coordination between a firm's own desks.
- **Prompt artefact.** The output format lists `"private_message": null` although the only channel is public. A few EXP2 replies filled it in; nothing was delivered.
- **Market measures not reported.** The study was pre-registered with hypotheses that are mostly about behavioural and market measures (deviations, markups, profits against a competitive benchmark). This repository no longer computes them. The pre-registrations are in the git history (commit `cd8db70`, `docs/experiments/`), and the earlier experiments (working names EXP0–EXP6) at `2ea0394`. The code exactly as EXP1–3 ran, including those measures, is at `cd8db70`. The current code reproduces every committed run's prompts, prices and profits (`tests/test_replay.py`).

## Credits and disclosures

- **New work, generated with Claude.** All code, including the simulation, was written during the sprint with Claude Code. No pre-existing code is included. The simulation's soundness has not yet been thoroughly reviewed (see above).
- **Design inspiration:** Agrawal et al. (2025), *Evaluating LLM Agent Collusion in Double Auctions* ([arXiv:2507.01413](https://arxiv.org/abs/2507.01413), [code](https://github.com/andyjliu/llm-agent-collusion)). We reuse ideas, not code: the market design inspired ours, and their reasoning-trace judge shaped our trace coder.
- **Dual use.** The market is deliberately stylised: one product, synthetic noise, and no real companies or data.
