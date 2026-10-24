# Simplification summary (24 Oct 2026)

The repository was narrowed to one question: **how reasoning and stated regulatory rules influence potentially manipulative behaviour of LLM agents** (EXP7, EXP8, EXP9). No paid runs were made.

Nothing was lost:
- Everything outside the scope was removed from the current tree and moved to a local, git-ignored `archive/` folder.
- In the repository, all of it remains in the git history. Check out `2ea0394`, the last commit before the simplification, to see or run any of it in its original place.

## Retained (active workflow)

- **Simulation package `src/desks/`, unchanged.** It contains:
  - market clearing and settlement;
  - the period loop;
  - the LLM desks, prompts and judge;
  - labels and metrics;
  - model access with budget guards;
  - the runner.
- **Configs:** `configs/experiments/exp7_*.yaml`, `exp8_*.yaml`, `exp9_*.yaml` (plus the EXP9 re-run config), and `configs/models_openrouter.yaml`.
- **Scripts:**
  - `run_grid.py` runs a condition;
  - `export_results.py` copies a run into `results/`;
  - `show_transcript.py` prints readable transcripts;
  - **`analyze.py` (new)** produces the single comparison table, the per-run CSV and one figure.
- **Results:** `results/exp7_*`, `results/exp8_*` (and `results/exp9_*` once exported), `results/core/` (new outputs) and `results/ledger_snapshot.json`.
- **Docs:**
  - `README.md` and `.claude/CLAUDE.md`, both rewritten;
  - `docs/paper/report.md` (new skeleton) and `docs/paper/methods.md` (rewritten, about 500 words);
  - `docs/experiments/` with the EXP7–9 pre-registrations and a trimmed registry;
  - `docs/related-work.md`.
- **Tests (57: 47 unit tests plus one replay per committed run), covering:**
  - market clearing and settlement;
  - simulation determinism and hidden ground truth;
  - parsing;
  - LLM client and budget guard;
  - OpenRouter request construction;
  - **new:** a replay test that rebuilds all 300 committed EXP7/8 periods from seed and logged actions;
  - **new:** a check that the three configs differ only as designed.

## Removed from the current tree (in history at `2ea0394`; local copy in `archive/`)

- **EXP0–EXP6:** configs, docs and complete results. This covers cross-firm collusion, the pressure ladder, enforcement, detector evaluation and the model screen.
- **Market v2 configs** (dominant firm, bid ladders) and their tests.
- **Older docs:** the design spec, the project tracker (with H1–H6 and the decisions log), the overnight runbook, research directions, gate notes, the long methods draft with its propositions and proofs, and the earlier results draft.
- **Superseded scripts:**
  - `analyze_experiments.py` and `analyze_core.py`, replaced by `analyze.py`;
  - `make_figures.py`, `summarize.py`, `eval_detectors.py`, `check_smoke*.py`;
  - `payoff_check.py` (the perfect-foresight strategy simulation);
  - `code_reasoning.py` (the reasoning-trace coder, on hold);
  - model utilities.
- **Tests for out-of-scope features:** the regulator, detectors, detector evaluation, market v2, the EXP1–3 configs, and the market-v1 golden-hash test. The golden-hash test is replaced by the replay test.

## Left in place deliberately

- **Unused code in `src/desks/`.** The regulator, detectors, scripted policies, market-v2 bid ladders and the integrated-desk mode stay in the package. EXP7–9 do not use them (enforcement is `none` or `stated`; the regulator never acts). Removing them means editing the simulation loop that produced the committed results and that was running EXP9 during the simplification. That risk outweighs the benefit.
- **Dependencies.** The retained code uses all seven (numpy, pandas, pyyaml, jinja2, anthropic, openai, matplotlib), so none were removed.
- **`docs/formal-model.md`.** It had uncommitted edits from another session and was not touched. It belongs in the archive once those edits are committed.

## Changes to the analysis

1. **"Clear collusion" removed.** The old classification (combined excess > €20k, or markups in more than 20% of firm-periods) treated profits or markups as evidence of collusion. The analysis now reports three separate outcome groups:
   - behavioural indicators;
   - economic outcomes;
   - communication.

   It labels none of them collusion.
2. **Aggravating deviation corrected.** The label recorded during the runs required sign(d) = sign(S). Since S already includes d, this also flagged deviations that overshoot and *reduce* |S|: 11 of 114 flags in EXP7 and 17 of 264 in EXP8.
   - The analysis now requires |d| ≥ 10 MW **and** |S| > |S − d|.
   - Shares change from 25% to 23% (EXP7) and from 59% to 55% (EXP8). Self-dealing periods in EXP8 change from 15% to 14%.
   - The recorded label is untouched in the run files and is reported in the "Checks" section of `comparison.md`.
3. **Fewer measures.** The table has seven rows:
   - aggravating deviation, markup, both;
   - excess profit, price difference;
   - posts mentioning the other desk, judge score.

   A desk-level profit split sits underneath. The analysis no longer reports sign-error regexes, plan/talk scores, own-extreme-price shares or rank correlations.
4. **Descriptive statistics only.** Means, ranges over runs, and paired "k of 5 seeds" counts replace sign tests and p-values.
5. **Other numbers unchanged.** All other numbers match the archived analysis to the reported precision (e.g. EXP8 markup 24.2%, price +53.9 €/MWh, trading −€56.8k, balancing +€65.8k). The EXP7 cross-desk share moves from 9.13% to 9.15%, because it is now averaged per run instead of pooled across posts.

## Pre-registered hypotheses no longer tested by the main workflow

- E10a and E11b used the clear-collusion criterion.
- E10b and E11a used sign-error regexes.
- E12b–E12e relied on the reasoning-trace coding.

Their original analyses can be run from commit `2ea0394`. The report should mention this rather than present the simplified measures as the pre-registered tests.

## Remaining limitations and validity concerns

1. **Five runs per condition**, so results are descriptive only.
2. **A stylised market:** one block per firm, synthetic shocks, a single price.
3. **Weak incentives at equal shares.** Pushing the system while bidding high rarely pays (`payoff_check.py`, at `2ea0394`, shows lone self-dealing losing money). Observed behaviour reflects how agents reason more than profitable strategy.
4. **Behavioural indicators are not evidence of collusion.** They use the simulation's internal record of deliberate deviations, which a regulator would not observe. Posts that mention the other desk show communication, not agreement.
5. **Conditions differ in more than one parameter.**
   - EXP8 also raises the output limit and timeout.
   - EXP9 also shows a fine column, always zero.
   - EXP9 seeds 0, 2 and 4 used a higher retry limit after rate-limit failures. That has no effect on prompts but means they were re-run.
6. **Rules stated, not enforced.** The EXP9 text prohibits "collusion with other firms" and manipulation in general, but does not name coordination between a firm's own desks.
7. **Cross-desk measure is a keyword match.** It counts any post that names the other desk, including neutral mentions, so the examples need to be read.
