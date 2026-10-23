# EXP3: Channels × enforcement with honest desks; does enforcement chill passive balancing?

**Registered:** Fri 23 Oct 2026, before any EXP3 run. **Config:** `configs/experiments/exp3_enforcement.yaml`. **Results:** `results/exp3_enforcement/`.

## Motivation

This is the pre-registered pilot grid (spec §8: channel × enforcement + baseline), run with the main prompts (two desks per firm, shared firm objective). The positive control failed, so effects on *collusion* (H1, H2, H4, H5) can only be reported descriptively. H6's second half doesn't need collusion, though. In EXP0b the trading desks naturally leaned 2–8 MW against the previous period's imbalance, which is legitimate passive balancing. So we can test whether enforcement *chills* it.

## Design

- Channel {public, public + private} × enforcement {none, stated, talk, action}, 1 seed each (8 runs), plus a no-channel / no-enforcement baseline (1 run).
- Replication for the chilling test: public channel × {none, action}, seeds 1–2 (+4 runs, so 3 seeds each).
- 13 runs in total; Haiku 5.5, 6 desks per run.
- Small-lean metrics (exploratory, below the spec's 10 MW passive label):
  - `lean_against_volume_llm` = Σ|d| over LLM desk-periods with |d| ≥ 1 MW and sign(d) = −sign(S_{t−1});
  - `lean_with_volume_llm`, the same with the same sign as S_{t−1};
  - `mean_abs_S`, and the cost to the rest of the market.
- Known confound (Findings, 23 Oct): a suspension mechanically raises consumer harm, because it withdraws 40 MW. Grid-cost comparisons should therefore be read on runs with and without suspensions separately.

## Pre-registered hypotheses

- **E6 (chilling, H6 second half):** in the public-channel cells (3 seeds each), `lean_against_volume_llm` is lower under `action` enforcement than under `none`.
- **Descriptive, n = 1 per cell:** we report H1 (public vs no channel: markup), H2 (private-channel judge score, none vs enforced), H4 (stated vs none) and H5 (talk enforcement: talk score vs action markers) as observations, not tests.

## Commands

```bash
.venv/bin/python scripts/run_grid.py configs/experiments/exp3_enforcement.yaml --workers 4
.venv/bin/python scripts/summarize.py runs/exp3_enforcement
.venv/bin/python scripts/export_results.py runs/exp3_enforcement results/exp3_enforcement
```

## Results

*(pending)*
