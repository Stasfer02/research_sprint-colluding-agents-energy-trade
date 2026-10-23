import numpy as np
import pytest

from desks.config import RegulatorConfig, RunConfig, run_config_from_dict
from desks.detectors import DetectorResult
from desks.regulator import Regulator, fine_amount
from desks.simulation import Simulation

from helpers import period


class AlwaysFlag:
    name = "always"

    def __init__(self, firms=("A",)):
        self.firms = firms

    def detect(self, firm, window, messages=None):
        return DetectorResult(firm in self.firms, 1.0, {})


def test_no_audits_without_enforcement():
    for enf in ("none", "stated"):
        reg = Regulator(RegulatorConfig(enforcement=enf), ("A", "B", "C"), AlwaysFlag(), np.zeros(30))
        recs = [period(t, -30) for t in range(1, 31)]
        assert all(reg.step(t, recs[:t], []) == [] for t in range(1, 31))


def test_ladder_and_cooldown():
    cfg = RegulatorConfig(enforcement="action", p_audit=1.0)
    reg = Regulator(cfg, ("A", "B", "C"), AlwaysFlag(), np.zeros(30))
    recs = [period(t, -30) for t in range(1, 31)]
    flags = []
    for t in range(1, 31):
        for ev in reg.step(t, recs[:t], []):
            if ev.flag:
                flags.append((t, ev.firm, ev.action))
    assert flags == [
        (5, "A", "warning"),
        (11, "A", "fine"),
        (17, "A", "fine+suspension"),
        (23, "A", "fine+suspension"),
        (29, "A", "fine+suspension"),
    ]


def test_audit_draws_gate_audits():
    cfg = RegulatorConfig(enforcement="action", p_audit=0.5)
    draws = np.ones(30)
    draws[6] = 0.1  # only period 7 audited
    reg = Regulator(cfg, ("A", "B", "C"), AlwaysFlag(), draws)
    recs = [period(t, -30) for t in range(1, 31)]
    audited = [t for t in range(1, 31) for ev in reg.step(t, recs[:t], []) if ev.audited]
    assert audited == [7, 7, 7]


def test_fine_amount():
    cfg = RegulatorConfig()
    win = [period(t, -30, A={"brp": 100.0, "bsp": 900.0, "comp": 0.0}) for t in range(1, 6)]
    assert fine_amount(win, "A", cfg) == pytest.approx(3 * 5000)
    assert fine_amount(win, "B", cfg) == cfg.min_fine


def test_suspension_removes_bsp_from_merit_order():
    cfg = run_config_from_dict({"seed": 1, "regulator": {"enforcement": "action", "p_audit": 1.0}})
    sim = Simulation(cfg)
    sim.regulator.detector = AlwaysFlag()
    sim.run()
    susp = [r["t"] for r in sim.records if r["firms"]["A"]["suspended"]]
    assert susp == list(range(18, 23)) + list(range(24, 29)) + [30]
    for r in sim.records:
        if r["firms"]["A"]["suspended"]:
            assert r["firms"]["A"]["q"] == 0
            assert len(r["public"]["merit_up"]) == 2
    fines = [r["firms"]["A"]["fine"] for r in sim.records]
    assert sum(f > 0 for f in fines) == 4
    assert all(r["firms"]["B"]["fine"] == 0 for r in sim.records)
    notices = [n["text"] for n in sim.notices]
    assert notices[0].startswith("REGULATOR NOTICE (period 5): Firm A received a warning")
