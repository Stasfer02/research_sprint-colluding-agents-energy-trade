"""Market v2 (design-spec §13): bid blocks, a dominant firm, the internal desk chat."""

import json
import re

import numpy as np
import pytest
import yaml

from desks.agents import CHANNEL_INTERNAL, INTRA_EXPLICIT_TEXT, LLMDesk
from desks.agents_base import Observation
from desks.channels import Channels
from desks.config import MarketParams, expand_grid, load_grid, run_config_from_dict
from desks.llm import BudgetGuard, FakeBackend, LLMClient
from desks.market import SHORT, benchmark, clear, firm_markup, make_units, settle
from desks.policies import WITHHOLD_DOWN, WITHHOLD_UP, ScriptedBSP
from desks.runner import run_one
from desks.simulation import Simulation

from fake_llm import role_of, valid_responder

with open("configs/market_v2.yaml") as fh:
    V2 = yaml.safe_load(fh)["market"]
P2 = MarketParams(blocks=V2["blocks"])


def test_units_v1_one_block_per_firm():
    u = make_units(MarketParams(), 3)
    assert u.one_per_firm
    np.testing.assert_array_equal(u.mw, [40, 40, 40])
    np.testing.assert_array_equal(u.c_up, [70, 75, 80])
    vals = np.array([1.0, -0.0, 2.0])
    assert u.by_firm(vals, 3) is not None and np.array_equal(u.by_firm(vals, 3), vals)


def test_units_v2_ladder():
    u = make_units(P2, 3)
    assert not u.one_per_firm
    np.testing.assert_array_equal(u.owner, [0, 0, 0, 0, 1, 2])
    np.testing.assert_array_equal(u.of(0), [0, 1, 2, 3])
    np.testing.assert_array_equal(u.by_firm(np.arange(6.0), 3), [6, 4, 5])
    with pytest.raises(ValueError):
        make_units(MarketParams(blocks=[[[20, 70, 55]], [[20, 78, 48]]]), 3)


def test_clear_and_settle_ladder_pivotal_block():
    u = make_units(P2, 3)
    up = u.c_up.copy()
    up[2:4] = 250.0  # A withholds its top two blocks
    keys = np.linspace(0.1, 0.6, 6)
    # need 90 MW: A1, A2 (cost bids), B, C, then A3 at 250 for 10 MW sets the price
    cl = clear(-90, up, u.c_down, u.mw, np.ones(6, bool), keys, P2)
    assert cl.direction == SHORT and cl.price == 250 and u.owner[cl.marginal] == 0
    np.testing.assert_allclose(cl.q, [20, 20, 10, 0, 20, 20])
    st = settle(np.zeros(3), -90, cl, u.c_up, u.c_down, P2.lam)
    np.testing.assert_allclose(u.by_firm(st.bsp, 3), [20 * 180 + 20 * 179 + 10 * 178, 20 * 172, 20 * 170])
    # balanced period: per-block zeros
    cl = clear(0.5, up, u.c_down, u.mw, np.ones(6, bool), keys, P2)
    assert settle(np.zeros(3), 0, cl, u.c_up, u.c_down, P2.lam).bsp.shape == (6,)


def test_benchmark_v2_per_block():
    S, cl, st = benchmark(np.array([-5.0, 0.0, 0.0]), -40.0, np.linspace(0.1, 0.6, 6), P2)
    assert cl.price == 72  # 45 MW: A1, A2 and 5 MW of A3
    assert st.bsp.shape == (6,)


def test_firm_markup_is_max_over_blocks():
    u = make_units(P2, 3)
    up = u.c_up.copy()
    up[3] = 146.0  # A4 cost 73 -> markup 1.0
    assert firm_markup(up, u.c_down, u, 0, SHORT) == pytest.approx(1.0)
    assert firm_markup(up, u.c_down, u, 1, SHORT) == 0


def test_scripted_withhold():
    a = ScriptedBSP("A", "withhold", [70, 71, 72, 73], [55, 54, 53, 52]).act(None)
    assert a.up_bids == [70, 71, WITHHOLD_UP, WITHHOLD_UP] and a.down_bids == [55, 54, WITHHOLD_DOWN, WITHHOLD_DOWN]
    assert a.up_bid is None
    single = ScriptedBSP("B", "withhold", 78.0, 48.0).act(None)
    assert (single.up_bid, single.down_bid) == (WITHHOLD_UP, WITHHOLD_DOWN)
    cartel = ScriptedBSP("A", "cartel", [70, 71], [55, 54]).act(None)
    assert cartel.up_bids == [300, 300] and cartel.down_bids == [0, 0]


def _sim2(**agents):
    return Simulation(run_config_from_dict({"seed": 3, "market": V2, "agents": agents, "channel": {"channel": "public_internal"}}))


def test_simulation_v2_benchmark_and_records():
    sim = _sim2()
    s = sim.run()
    assert all(abs(s[f"excess_{f}"]) < 1e-9 for f in "ABC") and abs(s["rest_harm"]) < 1e-9
    assert s["market_version"] == 2 and s["self_deal_rate"] == 0
    rec = sim.records[-1]
    assert len(rec["firms"]["A"]["u_blocks"]) == 4 and "u_blocks" not in rec["firms"]["B"]
    assert rec["firms"]["A"]["q"] == pytest.approx(sum(rec["firms"]["A"]["q_blocks"]))
    assert all(b["mw"] == 20 for b in rec["public"]["merit_up"] + rec["public"]["merit_down"])  # anonymous sizes
    assert len(rec["public"]["merit_up"]) == 6


def test_simulation_v2_self_deal_label_and_suspension_carry_over():
    sim = Simulation(run_config_from_dict({
        "seed": 3, "market": V2, "agents": {"brp": ["aggravate", "zero", "zero"], "bsp": ["withhold", "cost", "cost"]},
        "regulator": {"enforcement": "oracle", "p_audit": 1.0},
    }))
    s = sim.run()
    assert s["self_deal_rate_A"] > 0 and s["self_deal_rate_B"] == 0
    susp = [r for r in sim.records if r["firms"]["A"]["suspended"]]
    assert susp, "oracle enforcement with full audits should suspend A at some point"
    assert all(r["firms"]["A"]["q"] == 0 and len(r["firms"]["A"]["u_blocks"]) == 4 for r in susp)


def test_internal_channel_is_firm_private():
    ch = Channels("public_internal")
    ch.post(1, "A", "brp", "pub", None, "A internal")
    ch.post(1, "B", "bsp", None, None, "B internal")
    ch.post(1, "A", "integrated", None, None, "ignored")  # one agent has nobody to chat with
    assert [m["text"] for m in ch.internal(2, "A")] == ["A internal"]
    assert [m["text"] for m in ch.internal(2, "B")] == ["B internal"]
    assert ch.internal(1, "A") == []  # delivered next period
    assert [m["text"] for m in ch.public_messages()] == ["pub"]
    assert Channels("public").internal(2, "A") == []
    with pytest.raises(ValueError):
        Channels("internal_only")


def _client(tmp_path, responder):
    cfg = run_config_from_dict({}).llm
    return LLMClient(cfg, FakeBackend(responder), BudgetGuard(tmp_path / "l.json", 100.0, cfg.prices))


def _obs(role, t=1):
    return Observation(firm="A", role=role, t=t, T=30, S_prev=0.0, public_history=[], own_history=[], cum_profit=0.0,
                       profit_label="Firm A total profit")


def test_v2_prompts_and_ladder_parsing(tmp_path):
    cfg = run_config_from_dict({"market": V2, "channel": {"channel": "public_internal"}})
    bsp = LLMDesk("A", "bsp", cfg, _client(tmp_path, valid_responder))
    assert bsp.ladder and '"up_bids"' in bsp.system and '"up_bid"' not in bsp.system
    assert "block 4: 73 / 52" in bsp.system and "Firm A 80 MW (four blocks)" in bsp.system
    assert CHANNEL_INTERNAL.format(firm="A") in bsp.system and '"internal_message"' in bsp.system
    assert "short by 50 MW" in bsp.system and "for 10 MW" in bsp.system
    brp = LLMDesk("A", "brp", cfg, _client(tmp_path, valid_responder))
    assert not brp.ladder and '"up_bids"' not in brp.system and "Firm A's balancing desk" in brp.system
    small = LLMDesk("B", "bsp", cfg, _client(tmp_path, valid_responder))
    assert not small.ladder and '"up_bid"' in small.system and "each for a block of 20 MW" in small.system
    integ = LLMDesk("A", "integrated", cfg, _client(tmp_path, valid_responder))
    assert integ.ladder and not integ.has_internal and "Internal Chat" not in integ.system

    ok = json.dumps({"up_bids": [70, 71, 300, 2000], "down_bids": [55, 54, 0, -900], "internal_message": "hi",
                     "public_post": "p", "notes": "n"})
    a = LLMDesk("A", "bsp", cfg, _client(tmp_path, lambda *_: ok)).act(_obs("bsp"))
    assert a.parse_ok and a.up_bids == [70, 71, 300, 1000] and a.down_bids == [55, 54, 0, -200]
    assert a.internal_message == "hi"
    bad = json.dumps({"up_bids": [70, 71], "down_bids": [55, 54]})
    a = LLMDesk("A", "bsp", cfg, _client(tmp_path, lambda *_: bad)).act(_obs("bsp"))
    assert not a.parse_ok and a.up_bids == [70, 71, 72, 73]  # falls back to cost bids per block


def test_intra_explicit_pressure(tmp_path):
    cfg = run_config_from_dict({"market": V2, "agents": {"pressure": "intra_explicit"}})
    desk = LLMDesk("B", "brp", cfg, _client(tmp_path, valid_responder))
    assert INTRA_EXPLICIT_TEXT.format(firm="B") in desk.system


def v2_responder(system, messages, model):
    """valid_responder, with per-block bids for ladder desks and an internal message where there is a chat."""
    out = json.loads(valid_responder(system, messages, model).split("\n", 1)[1]) if role_of(system) != "judge" else None
    if out is None:
        return valid_responder(system, messages, model)
    if '"up_bids"' in system:
        n = int(re.search(r"\[<(\d) numbers", system).group(1))
        out.pop("up_bid"), out.pop("down_bid")
        out["up_bids"], out["down_bids"] = [90] * n, [40] * n
    if '"internal_message"' in system:
        out["internal_message"] = "internal note"
    return json.dumps(out)


def test_full_v2_llm_run_with_fake_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_USD", "5")
    cfg = expand_grid({"name": "t", "out_dir": str(tmp_path / "runs"), "seeds": 1, "base": {
        "market": V2, "agents": {"mode": "llm", "scripted_firms": {"B": {"brp": "zero", "bsp": "cost"}, "C": {"brp": "zero", "bsp": "cost"}}},
        "channel": {"channel": "public_internal"}, "llm": {"ledger_path": str(tmp_path / "ledger.json")},
    }})[0]
    assert run_one(cfg, backend=FakeBackend(v2_responder))["status"] == "ok"
    s = json.loads((cfg.run_dir / "summary.json").read_text())
    assert s["parse_failure_rate"] == 0 and s["llm_calls"] == 30 * 2
    assert s["n_internal_msgs"] == 30 * 2 and "judge_internal_A" in s and s["judge_internal_B"] == 0.0  # no chat
    periods = [json.loads(line) for line in (cfg.run_dir / "periods.jsonl").read_text().splitlines()]
    assert all(p["firms"]["A"]["u_blocks"] == [90] * 4 for p in periods)
    io = [json.loads(line) for line in (cfg.run_dir / "agent_io.jsonl").read_text().splitlines()]
    prompts = [e["prompt"] for e in io if e.get("desk") == "brp" and e.get("prompt")]
    assert "## Internal Chat with Firm A's balancing desk" in prompts[5] and "internal note" in prompts[5]


def test_load_grid_include(tmp_path):
    p = tmp_path / "g.yaml"
    p.write_text("name: g\ninclude: [configs/market_v2.yaml]\nbase: {market: {rho: 0.8}}\n")
    cfg = load_grid(p)[0]
    assert cfg.market.rho == 0.8 and len(cfg.market.blocks) == 3


def test_unequal_block_sizes_rejected(tmp_path):
    cfg = run_config_from_dict({"market": {"blocks": [[[40, 70, 55]], [[20, 78, 48]], [[20, 80, 45]]]}})
    with pytest.raises(ValueError):
        LLMDesk("A", "bsp", cfg, _client(tmp_path, valid_responder))
