import json

import numpy as np

from desks.config import expand_grid, run_config_from_dict
from desks.runner import run_one
from desks.simulation import Simulation


def _sim(**agents):
    return Simulation(run_config_from_dict({"seed": 7, "agents": agents, "channel": {"channel": "public_private"}}))


def test_deterministic():
    a, b = _sim(), _sim()
    a.run(), b.run()
    assert json.dumps(a.records) == json.dumps(b.records)


def test_noise_path_independent_of_behaviour():
    a = _sim()
    b = _sim(brp=["aggravate", "random", "passive"], bsp=["cartel", "markup", "cost"])
    a.run(), b.run()
    for ra, rb in zip(a.records, b.records):
        assert ra["r"] == rb["r"]
        assert ra["P_comp"] == rb["P_comp"] and ra["S_comp"] == rb["S_comp"]
        for f in "ABC":
            assert ra["firms"][f]["e"] == rb["firms"][f]["e"]
            assert ra["firms"][f]["comp"] == rb["firms"][f]["comp"]


def test_benchmark_profile_has_zero_excess():
    s = _sim().run()
    for f in "ABC":
        assert abs(s[f"excess_{f}"]) < 1e-9
    assert abs(s["rest_harm"]) < 1e-9


def test_observation_hides_ground_truth():
    sim = _sim(brp=["aggravate", "random", "passive"])
    sim.run()
    hidden_keys = {"e", "r", "d_others", "comp", "brp_comp", "bsp_comp", "marginal", "manip", "passive", "markup_flag"}
    for role in ("brp", "bsp", "integrated"):
        obs = sim._observation("A", role, 31, False)
        for row in obs.public_history:
            assert not hidden_keys & set(row)
            for bid in row["merit_up"] + row["merit_down"]:
                assert set(bid) == {"price", "mw", "activated_mw"}  # no firm IDs
        for row in obs.own_history:
            assert not hidden_keys & set(row)
        text = json.dumps(obs.__dict__)
        # other firms' deviations never appear
        for r in sim.records[-8:]:
            for f in "BC":
                d = r["firms"][f]["d"]
                if abs(d) > 1e-6:
                    assert repr(d) not in text
            assert repr(r["r"]) not in text
            assert repr(r["firms"]["A"]["e"]) not in text
    bsp = sim._observation("A", "bsp", 31, False)
    assert all("deviation_mw" not in row and "position_mw" not in row for row in bsp.own_history)
    brp = sim._observation("A", "brp", 31, False)
    assert all("up_bid" not in row for row in brp.own_history)


def test_messages_delivered_next_period():
    sim = _sim()
    sim.run()
    board = sim.channels.board(10)
    assert board and {m["t"] for m in board} == {8, 9}
    assert {m["channel"] for m in sim.channels.private(10)} <= {"private"}


def test_runner_resumable(tmp_path):
    runs = expand_grid({"name": "t", "out_dir": str(tmp_path), "seeds": 2, "base": {"market": {"T": 6}}})
    assert [run_one(r)["status"] for r in runs] == ["ok", "ok"]
    assert [run_one(r)["status"] for r in runs] == ["skipped", "skipped"]
    d = runs[0].run_dir
    for name in ("config.json", "periods.jsonl", "messages.jsonl", "regulator.jsonl", "agent_io.jsonl", "summary.json"):
        assert (d / name).exists()
    assert len((d / "periods.jsonl").read_text().splitlines()) == 6


def test_grid_expansion():
    runs = expand_grid({
        "name": "g", "seeds": 2,
        "grid": {"channel.channel": ["public", "public_private"], "regulator.enforcement": ["none", "talk"]},
        "cells": [{"id": "x"}, {"id": "base", "grid": False, "seeds": 1, "channel": {"channel": "none"}}],
    })
    assert len(runs) == 2 * 2 * 2 + 1
    assert runs[0].cell_id == "x__channel-public__enforcement-none"
    assert runs[-1].cell_id == "base" and runs[-1].channel.channel == "none"
