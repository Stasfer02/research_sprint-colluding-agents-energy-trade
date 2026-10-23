# EXP0: gate runs (Fri 23 Oct 2026)

These runs predate per-run `provenance.json`, so the code version each one used is reconstructed from the git history below. `git_dirty` means the working tree had changes that were committed in the next commit listed.

| Folder | Config | Code version | Outcome |
|---|---|---|---|
| `smoke/` (aggregates only; deterministic, regenerate with `scripts/run_grid.py configs/smoke.yaml`) | `configs/smoke.yaml` | `59a6a72` | Gates 1–2 pass (`scripts/check_smoke.py`) |
| `llm_single_v1/` | `configs/llm_single.yaml` | `59a6a72` (clean, plus untracked `scripts/show_transcript.py`) | Prompt bugs found; see `docs/notes/llm_single-review.md` |
| `llm_single/` | `configs/llm_single.yaml` | dirty on `59a6a72`, changes committed in `fb54644` (excluding the later `notes_regulator_words` regex fix) | Gate 3 pass |
| `positive_control_v1/` | `configs/positive_control.yaml` | `fb54644` (clean) | Gate 4 fail |
| `positive_control/` | `configs/positive_control.yaml` | dirty on `fb54644`, payoff-clarity lines committed in `4e82066` | Gate 4 fail; see `docs/notes/positive_control-review.md` |

Each run folder has `config.json`, `summary.json`, `messages.jsonl`, `judge.json`, `regulator.jsonl`, and the gzipped `periods.jsonl.gz` and `agent_io.jsonl.gz` (full prompts and raw model outputs). Read one with:

```bash
gunzip -k results/exp0_gates/positive_control/runs/default/seed_0/*.gz
.venv/bin/python scripts/show_transcript.py results/exp0_gates/positive_control/runs/default/seed_0
```
