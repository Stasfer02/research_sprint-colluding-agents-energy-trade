# Overnight runbook — Fri 23 → Sat 24 Oct 2026

Written with Stan on Fri 23 Oct, ~22:00 Amsterdam. Claude Code works through this file unattended. If a session is resumed or compacted, re-read this file and `docs/project-tracker.md`, check `git log`, and continue from the first unticked item.

## Standing authorisations (agreed with Stan)

- **Work without asking.** Don't stop for questions. Pick the smallest reasonable choice, record it in the tracker's Decisions log (or Open questions), and keep going.
- **API spend:** allowed up to and including the **pilot grid**, with `BUDGET_USD = 5` for the overnight session (ledger-enforced). Model: `claude-haiku-5-5` only. Do **not** start `full.yaml`. Do not raise the cap or switch models.
- **Gates still apply** (CLAUDE.md rule 4): each LLM stage starts only when the previous gate passed. If a gate fails and can't be fixed cleanly, stop spending and continue with work that doesn't depend on it.
- **Parameter tweaks:** if the smoke grid doesn't reproduce §2.6 signs *after ruling out bugs*, the smallest parameter change that restores them is allowed — log it with before/after numbers. Proceed to LLM stages on changed parameters only if the change is a single, clearly justified value; otherwise stop spending and flag it.
- **Git:** commit on `dev` at each gate / component (small, descriptive commits), push to `origin/dev`. Never force-push, never touch `main`, never commit `.env` or `runs/`.
- **Secrets:** never read, print or `cat` `.env`. Code loads it into the environment; tests never need a real key.
- **Python:** use `.venv/bin/python` / `.venv/bin/pytest` (Python 3.12, deps pre-installed). Long runs: Bash tool with `run_in_background` (`.venv/bin/python scripts/run_grid.py ...`; the runner writes its own log under `runs/`).
- **Permissions (no Bypass mode):** only these shell commands are pre-approved in `.claude/settings.json` — anything else prompts and stalls the night: `.venv/bin/python`, `.venv/bin/pytest`, `uv pip install`, `git status|diff|log|add|commit`, `git push origin dev`, `ls`, `mkdir`, `tail`, `wc`. One command per Bash call — no `cd … &&`, no pipes into other tools, no `cat`/`grep`/`find` (use the Read tool; do file inspection in Python if needed). Stay inside the repo.

## Checklist

### A. Build — no API cost (spec §10 steps 1–4)
- [x] A1. Skeleton: `pyproject.toml` (installable `-e ".[dev]"`), `src/desks/`, `config.py` (dataclasses + YAML loader, resolved-config dump), `.env.example`, README stub (credits Agrawal et al. design, sprint disclosure). Commit.
- [x] A2. `market.py` (pure clearing, settlement, benchmark) + `tests/test_market.py` with hand-computed cases: short, long, balanced/mid-price, cap, floor, ties (seeded), suspension, clamping. Commit.
- [x] A3. `policies.py`, `simulation.py` (separate RNG streams: noise / tie-break / audit), logging per spec §9, `metrics.py`, `configs/smoke.yaml`, `scripts/run_grid.py` (minimal), `scripts/check_smoke.py`. **Gate 1:** smoke reproduces §2.6 signs. Record numbers vs planning table in tracker Findings. Commit + push.
- [x] A4. `labels.py`, `detectors.py` (action, oracle, keyword talk), `regulator.py` (audit, ladder, fines, notices, cooldown, suspension) + tests. Smoke with enforcement {none, action, oracle}: detectors flag aggravate/cartel, not zero. **Gate 2.** Commit + push.

### B. LLM plumbing — no API cost (steps 5–6, 8)
- [ ] B1. `llm.py`: anthropic + openai_compatible backends, retries/backoff, 60 s timeout, budget guard with file-locked `runs/ledger.json`, price table in config. Fake client for tests.
- [ ] B2. Prompts (`brp.j2`, `bsp.j2`, `integrated.j2`, `judge.j2`), `agents.py` (rendering, JSON parse + one retry + fallback, clamping, notes), `channels.py`. Tests: parsing, info hiding (prompts never contain `e`, `r`, others' `d`, firm IDs in merit order), full sim with fake client. Add `objective: shared|separate` config option (cheap; tracker open question).
- [ ] B3. `run_grid.py` full: grid expansion, resumable (skip runs with `summary.json`), `--workers`, clean stop on budget exhaustion. `summarize.py`: CSV + 3 plots. Commit + push.
- [ ] B4. `eval_detectors.py` (seed split, thresholds on split 1, P/R/FPR on split 2, FPR on hard negatives, held-out detector in enforced cells) — validate on scripted runs incl. passive profiles. Commit + push.

### C. LLM stages — spends money (step 7)
- [ ] C0. Sanity: one API call through the budget guard; confirm reported token usage and ledger cost look right.
- [ ] C1. `llm_single.yaml` → read the full transcript. Write `docs/notes/llm_single-review.md`: do agents understand the market, parse rate, sensible actions, any prompt bugs. Fix prompt *clarity* bugs (not hypotheses) and re-run once if needed. **Gate 3.**
- [ ] C2. `positive_control.yaml` (3 seeds). **Gate 4:** clear excess profit and/or aggravation/markup above benchmark. If not, improve payoff clarity in prompts (log it), re-run once; if still not, stop spending and write up.
- [ ] C3. `pilot.yaml` (9 runs). Summarise; fix bugs; note results in Findings (labelled pilot, n=1 per cell — no conclusions about H1–H6).

### D. Morning handoff
- [ ] D1. Tracker updated (status, checklist, decisions, findings, changelog).
- [ ] D2. Write a **"Morning handoff"** section at the top of the tracker: what's done, gate results with numbers, spend so far, decisions Stan should review, open questions, suggested next steps for Saturday (incl. readiness for `full.yaml`).
- [ ] D3. Final commit + push.

## If stuck

- A failing test you can't fix in ~30 min: mark `xfail` with a reason, log it, move on.
- API errors / rate limits: back off; if persistent, stop section C and finish A/B/D.
- Budget guard trips: stop cleanly, record, go to D.
