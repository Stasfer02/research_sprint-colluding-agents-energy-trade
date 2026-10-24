# Experiment registry

Every experiment has an ID, a config in `configs/`, a doc here (question, design, pre-registered hypotheses, commands, results) and committed outputs in `results/<id>/`. Raw run directories live in `runs/` (git-ignored). `scripts/export_results.py` copies them into `results/`, keeping full prompts and raw model outputs gzipped. LLM sampling can't be seeded (the API has no temperature or seed control), so those files are what makes an LLM analysis reproducible.

**Provenance.** Every run writes `provenance.json`: git commit, dirty flag, a hash of the prompt templates and constants, package versions and start time. `summary.json` repeats the commit and prompt hash. `scripts/run_grid.py` refuses to start LLM runs from a dirty working tree.

**Two market versions.**
- **Market v1** (three symmetric firms; tests cross-firm collusion): EXP0a–EXP5. The code is tagged `market-v1` (commit `c16f017`), and results are in `results/exp0_gates`, `results/exp1_*` to `results/exp5_*`.
- **Market v2** (a dominant Firm A; tests intra-firm self-dealing between a firm's own trading and balancing desks; design-spec §13): EXP0d onward.

v2 is opt-in through `market.blocks`. Without it, current code reproduces every v1 config byte for byte (records, summaries and prompts), so v1 results can be re-run from `dev` or from the tag.

**Pre-registration.** The project hypotheses H1–H6 are fixed in `docs/project-tracker.md` §4. Hypotheses for the experiments below (E2–E6) were added to the tracker's Exploratory table and to these docs **before** their runs; the commit history shows the order.

| ID | Question | Config | Hypotheses | Status | Results |
|---|---|---|---|---|---|
| EXP0a | Do scripted policies reproduce the incentive structure? Do detectors flag the right profiles? (gates 1–2) | `configs/smoke.yaml` | spec §2.6 signs | done, pass | `results/exp0_gates/smoke` |
| EXP0b | Do LLM desks understand the market? (gate 3) | `configs/llm_single.yaml` | — | done, pass (v2) | `results/exp0_gates/llm_single{,_v1}`, `docs/notes/llm_single-review.md` |
| EXP0c | Positive control: do LLM agents collude when allowed? (gate 4) | `configs/positive_control.yaml` | — (E1 added after) | done, **fail ×2** | `results/exp0_gates/positive_control{,_v1}`, `docs/notes/positive_control-review.md` |
| [EXP1](exp1_detection.md) | What counts as evidence: talk vs action detectors | `configs/experiments/exp1_detection.yaml` | E2a–c, E3 | done: E2a, E2b, E2c, E3 supported | `results/exp1_detection` |
| [EXP2](exp2_pressure.md) | Collusion-pressure ladder: what does it take? | `configs/experiments/exp2_pressure.yaml` | E4, E5 | done: E4 not supported (no collusion at any level); E5 "declined" (75% decline, 66% escalate) | `results/exp2_pressure` |
| [EXP3](exp3_enforcement.md) | Channels × enforcement with honest desks; chilling of passive balancing | `configs/experiments/exp3_enforcement.yaml` | E6 (+ H1, H2, H4–H6 descriptive) | done: E6 direction supported (41 vs 12 MW, p = 0.10) | `results/exp3_enforcement` |

| [EXP4](exp4_model_screen.md) | Multi-model collusion screen (OpenRouter) | `configs/experiments/exp4_model_screen.yaml` | E7a–c (never tested) | **withdrawn** before any run completed | none |
| [EXP5](exp5_deepseek_gate.md) | Gate replication with DeepSeek-V4-Flash: does another model collude under pressure? | `configs/experiments/exp5_deepseek_gate.yaml` + `configs/models_openrouter.yaml` | E8a–c | done: **DeepSeek colludes** (explicit: 3/3 runs, 99% cartel-level bids, +€52k/run); E8a, E8b supported, E8c not | `results/exp5_deepseek_gate` |
| EXP0d | **Market v2** gate: does intra-firm self-dealing pay for the dominant firm, and only when both desks take part? Do detectors flag it? | `configs/smoke_v2.yaml` (+ `configs/market_v2.yaml`) | design-spec §13.4 | done, **pass 16/16** (A self-deals +€9.1k/run; trading desk alone −€0.5k) | `results/exp0_gates/smoke_v2` |
| [EXP7](exp7_deepseek_desks.md) | Baseline (market v1, equal shares): six DeepSeek desks, public board only, collusion never mentioned | `configs/experiments/exp7_deepseek_desks.yaml` | E10a–b | done: **no collusion, 0 self-dealing periods** (E10a); 25% aggravating deviations, driven by a profit-sign misunderstanding in 38% of trading-desk plans (E10b) | `results/exp7_deepseek_desks` |
| [EXP8](exp8_deepseek_desks_reasoning.md) | EXP7 with reasoning on (effort high) | `configs/experiments/exp8_deepseek_desks_reasoning.yaml` | E11a–c | done: sign error fixed (38% → 3%, E11a); **desks manipulate the price for their own firm even at equal shares**, coordinating via the public board; 5/5 runs meet the markup criterion (E11b not supported); profits swing ±€100k, not reliably positive | `results/exp8_deepseek_desks_reasoning` |
| [EXP6](exp6_intrafirm.md) | **Market v2:** do a firm's trading and balancing desks self-deal when it pays? | `configs/experiments/exp6_intrafirm.yaml` | E9a–e (draft) | **designed, not run** (awaits approval) | none |

Future directions (not yet registered) are in [docs/research-directions.md](../research-directions.md).

All hypothesis tests come from one script: `scripts/analyze_experiments.py`, which writes `results/analysis/hypotheses.{md,json}`. Spend across all LLM work is in `results/ledger_snapshot.json` ($4.42, 8,174 calls).

## Reproducing

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/pytest -q
git checkout <commit from results/<id>/runs/**/provenance.json>
.venv/bin/python scripts/run_grid.py <config> --workers 4             # LLM runs re-sample (not bit-identical)
.venv/bin/python scripts/summarize.py runs/<id>
.venv/bin/python scripts/eval_detectors.py runs/<id> [--judge --judge-private]
```

The scripted grids (EXP0a) are deterministic given the seed and reproduce exactly.
