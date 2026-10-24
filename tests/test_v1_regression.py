"""Market v1 stays reproducible: records, summaries and rendered prompts must match hashes taken from the
`market-v1` tag (commit c16f017). LLM configs run with a fake backend, so prompts are checked without API calls.
Regenerating `golden_v1.json` is only legitimate if a v1 change is intended and recorded in the tracker."""

import hashlib
import json
from pathlib import Path

import pytest

from desks.agents import build_judge, build_llm_desks
from desks.config import load_grid
from desks.llm import BudgetGuard, FakeBackend, LLMClient
from desks.simulation import Simulation, _json_default

from fake_llm import valid_responder

GOLDEN = json.loads((Path(__file__).parent / "golden_v1.json").read_text())


def _h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=_json_default).encode()).hexdigest()[:16]


def _cases():
    configs = sorted({k.split("::")[0] for k in GOLDEN})
    for name in configs:
        path = Path("configs") / name if (Path("configs") / name).exists() else Path("configs/experiments") / name
        for cfg in load_grid(path):
            if f"{name}::{cfg.cell_id}::{cfg.seed}" in GOLDEN:
                yield pytest.param(name, cfg, id=f"{name}::{cfg.cell_id}::{cfg.seed}")


@pytest.mark.parametrize("name,cfg", list(_cases()))
def test_v1_run_is_byte_identical(name, cfg, tmp_path):
    want = GOLDEN[f"{name}::{cfg.cell_id}::{cfg.seed}"]
    prompts = []
    if cfg.agents.mode == "llm":
        def responder(system, messages, model):
            prompts.append([system, messages])
            return valid_responder(system, messages, model)

        models = {cfg.llm.model, cfg.llm.judge_model, *cfg.agents.firm_models.values()}
        cfg.llm.prices = {m: {"input": 0.0, "output": 0.0} for m in models}
        client = LLMClient(cfg.llm, FakeBackend(responder), BudgetGuard(tmp_path / "l.json", 1e9, cfg.llm.prices))
        sim = Simulation(cfg, desks=build_llm_desks(cfg, client), judge=build_judge(cfg, client))
    else:
        sim = Simulation(cfg)
    summary = sim.run()
    summary.pop("wall_time_s", None)
    assert _h(sim.records) == want["records"]
    assert _h(summary) == want["summary"]
    if "prompts" in want:
        assert len(prompts) == want["n_prompts"]
        assert _h(sorted(json.dumps(p, default=_json_default) for p in prompts)) == want["prompts"]
