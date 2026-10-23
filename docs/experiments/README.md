# Experiment registry

Every experiment has an ID, a config in `configs/`, a doc here (question, design, pre-registered hypotheses, commands, results) and committed outputs in `results/<id>/`. Raw run directories live in `runs/` (git-ignored). `scripts/export_results.py` copies them into `results/`, keeping full prompts and raw model outputs gzipped. LLM sampling can't be seeded (the API has no temperature or seed control), so those files are what makes an LLM analysis reproducible.

**Provenance.** Every run writes `provenance.json`: git commit, dirty flag, a hash of the prompt templates and constants, package versions and start time. `summary.json` repeats the commit and prompt hash. `scripts/run_grid.py` refuses to start LLM runs from a dirty working tree.

**Pre-registration.** The project hypotheses H1–H6 are fixed in `docs/project-tracker.md` §4. Hypotheses for the experiments below (E2–E6) were added to the tracker's Exploratory table and to these docs **before** their runs; the commit history shows the order.

| ID | Question | Config | Hypotheses | Status | Results |
|---|---|---|---|---|---|
| EXP0a | Do scripted policies reproduce the incentive structure? Do detectors flag the right profiles? (gates 1–2) | `configs/smoke.yaml` | spec §2.6 signs | done, pass | `results/exp0_gates/smoke` |
| EXP0b | Do LLM desks understand the market? (gate 3) | `configs/llm_single.yaml` | — | done, pass (v2) | `results/exp0_gates/llm_single{,_v1}`, `docs/notes/llm_single-review.md` |
| EXP0c | Positive control: do LLM agents collude when allowed? (gate 4) | `configs/positive_control.yaml` | — (E1 added after) | done, **fail ×2** | `results/exp0_gates/positive_control{,_v1}`, `docs/notes/positive_control-review.md` |
| [EXP1](exp1_detection.md) | What counts as evidence: talk vs action detectors | `configs/experiments/exp1_detection.yaml` | E2a–c, E3 | registered | `results/exp1_detection` |
| [EXP2](exp2_pressure.md) | Collusion-pressure ladder: what does it take? | `configs/experiments/exp2_pressure.yaml` | E4, E5 | registered | `results/exp2_pressure` |
| [EXP3](exp3_enforcement.md) | Channels × enforcement with honest desks; chilling of passive balancing | `configs/experiments/exp3_enforcement.yaml` | E6 (+ H1, H2, H4–H6 descriptive) | registered | `results/exp3_enforcement` |

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
