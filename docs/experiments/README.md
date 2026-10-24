# Experiments

The study has three conditions on the same market and agents. Each condition has a doc with its question, design and pre-registered hypotheses, written and committed before its runs. That record is kept unchanged.

| ID | Condition | Config | Pre-registration | Results |
|---|---|---|---|---|
| [EXP7](exp7_deepseek_desks.md) | Baseline: reasoning off | `configs/experiments/exp7_deepseek_desks.yaml` | E10a–b (`b075e6b`) | `results/exp7_deepseek_desks` |
| [EXP8](exp8_deepseek_desks_reasoning.md) | Reasoning: effort "high" | `configs/experiments/exp8_deepseek_desks_reasoning.yaml` | E11a–c (`3df07be`) | `results/exp8_deepseek_desks_reasoning` |
| [EXP9](exp9_deepseek_desks_rules.md) | Compliance: EXP8 + REMIT text, not enforced | `configs/experiments/exp9_deepseek_desks_rules.yaml` (seeds 0, 2 and 4 re-run with `…_rerun.yaml`) | E12a–f (`514d646`) | `results/exp9_deepseek_desks_rules` |

**Main analysis.** The report's analysis is `scripts/analyze.py`, which writes `results/core/comparison.md`. Some pre-registered hypotheses relied on measures the simplified workflow no longer computes:
- the clear-collusion criterion of E10a and E11b, which has been dropped;
- regex sign-error measures (E10b, E11a);
- the reasoning-trace coding behind E12b–e, which is on hold.

Their original analyses (`scripts/analyze_experiments.py`, `results/analysis/`) can be run from commit `2ea0394`. See `docs/simplification.md`.

**Earlier experiments.** EXP0–EXP6 used other setups (cross-firm collusion, enforcement, market v2). Their docs, configs and complete results are in the git history at commit `2ea0394`.
