"""Period loop, observation building and per-run logging (spec §2.2, §9)."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from . import FIRMS
from .agents_base import Action, Desk, Observation
from .channels import Channels
from .config import RunConfig
from .detectors import ActionDetector, KeywordTalkDetector, OracleDetector
from .labels import period_labels
from .market import benchmark, bsp_costs, clamp_bids, clear, firm_markup, make_units, settle
from .metrics import summarize
from .policies import ScriptedBRP, ScriptedBSP
from .regulator import Regulator

NOTICES_SHOWN = 5


class JsonlWriter:
    def __init__(self, run_dir: Path | None):
        self.run_dir = run_dir
        self.handles: dict[str, Any] = {}
        if run_dir is not None:
            run_dir.mkdir(parents=True, exist_ok=True)
            for name in ("periods", "agent_io", "messages", "regulator"):
                self.handles[name] = open(run_dir / f"{name}.jsonl", "w")

    def write(self, name: str, obj: dict[str, Any]) -> None:
        h = self.handles.get(name)
        if h is not None:
            h.write(json.dumps(obj, default=_json_default) + "\n")
            h.flush()

    def close(self) -> None:
        for h in self.handles.values():
            h.close()


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def make_streams(seed: int, T: int, n: int, sigma_f: float, sigma_r: float, rho: float, n_units: int | None = None):
    """Separate RNG streams: market noise, tie-breaking, regulator audits, scripted-policy randomness.

    Everything except policy randomness is drawn up front, so agent behaviour never changes the noise path.
    Tie-break keys are drawn per bid block (`n_units`; market v1: one block per firm).
    """
    noise_ss, tie_ss, audit_ss, policy_ss = np.random.SeedSequence(seed).spawn(4)
    rng_noise = np.random.default_rng(noise_ss)
    e = rng_noise.normal(0.0, sigma_f, (T, n))
    eps = rng_noise.normal(0.0, sigma_r, T)
    r = np.zeros(T)
    prev = 0.0
    for t in range(T):
        prev = rho * prev + eps[t]
        r[t] = prev
    tie = np.random.default_rng(tie_ss).random((T, n_units or n))
    audit = np.random.default_rng(audit_ss).random(T)
    return e, r, tie, audit, np.random.default_rng(policy_ss)


def build_scripted_desks(cfg: RunConfig, rng_policy: np.random.Generator) -> dict[str, dict[str, Desk]]:
    m, a = cfg.market, cfg.agents
    units = make_units(m, len(FIRMS))
    return {
        f: {
            "brp": ScriptedBRP(f, a.brp[i], m.D, rng_policy),
            "bsp": ScriptedBSP(f, a.bsp[i], *bsp_costs(m, units, i)),
        }
        for i, f in enumerate(FIRMS)
    }


def make_enforcing_detector(cfg: RunConfig, judge=None):
    enf = cfg.regulator.enforcement
    if enf == "action":
        return ActionDetector(cfg.regulator.action)
    if enf == "oracle":
        return OracleDetector()
    if enf == "talk":
        kind = cfg.regulator.talk_detector
        if kind == "auto":
            kind = "judge" if cfg.agents.mode == "llm" else "keyword"
        if kind == "judge":
            if judge is None:
                raise ValueError("talk enforcement with judge detector needs a judge")
            return judge
        return KeywordTalkDetector(cfg.regulator.talk_flag_score)
    return None


class Simulation:
    def __init__(
        self,
        cfg: RunConfig,
        desks: dict[str, dict[str, Desk]] | None = None,
        judge=None,
        run_dir: Path | None = None,
    ):
        self.cfg = cfg
        m = cfg.market
        self.firms = FIRMS
        self.n = len(FIRMS)
        self.units = make_units(m, self.n)
        self.e, self.r, self.tie, self.audit, rng_policy = make_streams(
            cfg.seed, m.T, self.n, m.sigma_f, m.sigma_r, m.rho, n_units=len(self.units.mw)
        )
        self.desks = desks if desks is not None else build_scripted_desks(cfg, rng_policy)
        self.judge = judge
        self.channels = Channels(cfg.channel.channel, cfg.channel.board_periods, cfg.channel.max_chars)
        self.regulator = Regulator(cfg.regulator, self.firms, make_enforcing_detector(cfg, judge), self.audit)
        self.run_dir = run_dir
        # firm-level costs = each firm's first block (market v1: its only block)
        first = [self.units.of(i)[0] for i in range(self.n)]
        self.c_up = self.units.c_up[first]
        self.c_down = self.units.c_down[first]
        self.holding = cfg.agents.pressure in ("holding", "target", "explicit")
        self.records: list[dict[str, Any]] = []
        self.reg_events: list[dict[str, Any]] = []
        self.notices: list[dict[str, Any]] = []
        self.io_stats: list[dict[str, Any]] = []
        self.agent_notes: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ observations
    def _observation(self, firm: str, role: str, t: int, suspended: bool) -> Observation:
        H = self.cfg.agents.history_window
        i = self.firms.index(firm)
        recent = self.records[-H:]
        public = [rec["public"] for rec in recent]
        own = []
        for rec in recent:
            f = rec["firms"][firm]
            row: dict[str, Any] = {"t": rec["t"]}
            if role in ("brp", "integrated"):
                row.update(deviation_mw=f["d"], position_mw=f["x"], brp_pnl=f["brp"])
            if role in ("bsp", "integrated"):
                row.update(up_bid=f["u"], down_bid=f["v"], activated_mw=f["q"], bsp_pnl=f["bsp"], suspended=f["suspended"])
                if "u_blocks" in f:
                    row.update(up_bids=f["u_blocks"], down_bids=f["v_blocks"], activated_blocks=f["q_blocks"])
            row["fine"] = f["fine"]
            own.append(row)
        objective = "firm" if (role == "integrated" or self.cfg.agents.objective == "shared") else "desk"
        show_fines = self.cfg.regulator.enforcement != "none"
        brp = sum(rec["firms"][firm]["brp"] for rec in self.records)
        bsp = sum(rec["firms"][firm]["bsp"] for rec in self.records)
        fines = sum(rec["firms"][firm]["fine"] for rec in self.records)
        if objective == "firm":
            total = brp + bsp - fines
            label = f"Firm {firm} total profit (both desks{', after fines' if show_fines else ''})"
        else:
            total = (brp if role == "brp" else bsp) - fines
            label = f"Your desk's profit{' (after fines)' if show_fines else ''}"
        return Observation(
            firm=firm, role=role, t=t, T=self.cfg.market.T,
            S_prev=self.records[-1]["S"] if self.records else 0.0,
            public_history=public, own_history=own, cum_profit=total, profit_label=label,
            board=self.channels.board(t), private=self.channels.private(t),
            notices=self.notices[-NOTICES_SHOWN:], suspended=suspended,
            c_up=float(self.c_up[i]), c_down=float(self.c_down[i]),
            brp_profit=brp, bsp_profit=bsp, fines_total=fines, show_fines=show_fines,
            holding_profit=self._holding_profit() if self.holding else None,
            internal=self.channels.internal(t, firm) if role != "integrated" else [],
        )

    def _holding_profit(self) -> float:
        return sum(f["brp"] + f["bsp"] - f["fine"] for rec in self.records for f in rec["firms"].values())

    def _collect_actions(self, t: int, suspended: dict[str, bool]) -> dict[tuple[str, str], Action]:
        jobs = []
        for firm in self.firms:
            for role, desk in self.desks[firm].items():
                jobs.append((firm, role, desk))
        last = self.records[-1]["firms"] if self.records else None

        def run(job):
            firm, role, desk = job
            if role == "bsp" and suspended[firm]:
                prev = last[firm] if last else None
                i = self.firms.index(firm)
                idx = self.units.of(i)
                if len(idx) > 1:  # ladder: carry the block bids over
                    return Action(
                        up_bids=prev["u_blocks"] if prev else list(self.units.c_up[idx]),
                        down_bids=prev["v_blocks"] if prev else list(self.units.c_down[idx]),
                        io=[{"skipped": "suspended"}],
                    )
                return Action(
                    up_bid=prev["u"] if prev else self.c_up[i],
                    down_bid=prev["v"] if prev else self.c_down[i],
                    io=[{"skipped": "suspended"}],
                )
            return desk.act(self._observation(firm, role, t, suspended[firm]))

        if self.cfg.agents.mode == "llm" and len(jobs) > 1:
            with ThreadPoolExecutor(max_workers=self.cfg.llm.desk_workers) as pool:
                results = list(pool.map(run, jobs))
        else:
            results = [run(j) for j in jobs]
        return {(firm, role): res for (firm, role, _), res in zip(jobs, results)}

    # ------------------------------------------------------------------ main loop
    def run(self) -> dict[str, Any]:
        cfg, m = self.cfg, self.cfg.market
        log = JsonlWriter(self.run_dir)
        if self.run_dir is not None:
            (self.run_dir / "config.json").write_text(json.dumps(cfg.to_dict(), indent=2, default=_json_default))
        t0 = time.time()
        suspended_until = {f: 0 for f in self.firms}
        try:
            for t in range(1, m.T + 1):
                k = t - 1
                suspended = {f: suspended_until[f] >= t for f in self.firms}
                actions = self._collect_actions(t, suspended)

                units = self.units
                d = np.zeros(self.n)
                u = units.c_up.copy()  # per block (market v1: per firm)
                v = units.c_down.copy()
                for i, f in enumerate(self.firms):
                    idx = units.of(i)
                    for role in self.desks[f]:
                        a = actions[(f, role)]
                        if a.deviation is not None and role in ("brp", "integrated"):
                            d[i] = a.deviation
                        if role in ("bsp", "integrated"):
                            if a.up_bids is not None:
                                u[idx] = a.up_bids
                            elif a.up_bid is not None:
                                u[idx] = a.up_bid
                            if a.down_bids is not None:
                                v[idx] = a.down_bids
                            elif a.down_bid is not None:
                                v[idx] = a.down_bid
                        self.channels.post(t, f, role, a.public_post, a.private_message, a.internal_message)
                        for entry in a.io:
                            log.write("agent_io", {"t": t, "firm": f, "desk": role, **entry})
                            if "input_tokens" in entry:
                                self.io_stats.append(entry)
                        if a.notes is not None:
                            self.agent_notes.append({"t": t, "firm": f, "desk": role, "notes": a.notes})
                        if a.io and not a.parse_ok:
                            self.io_stats.append({"parse_fail": True})
                d = np.clip(d, -m.D, m.D)
                u, v, clamped = clamp_bids(u, v, m)
                eligible = np.array([not suspended[self.firms[o]] for o in units.owner])

                e, r, keys = self.e[k], float(self.r[k]), self.tie[k]
                x = e + d
                S = float(x.sum() + r)
                cl = clear(S, u, v, units.mw, eligible, keys, m)
                st = settle(x, r, cl, units.c_up, units.c_down, m.lam)
                S_c, cl_c, st_c = benchmark(e, r, keys, m)
                cl_cc = clear(S, units.c_up, units.c_down, units.mw, eligible, keys, m)
                st_cc = settle(x, r, cl_cc, units.c_up, units.c_down, m.lam)
                S_prev = self.records[-1]["S"] if self.records else 0.0
                # block-level quantities summed per firm (market v1: unchanged)
                q_f = units.by_firm(cl.q, self.n)
                bsp_f = units.by_firm(st.bsp, self.n)
                bsp_c_f = units.by_firm(st_c.bsp, self.n)
                bsp_cc_f = units.by_firm(st_cc.bsp, self.n)

                firms_rec = {}
                for i, f in enumerate(self.firms):
                    idx = units.of(i)
                    mk = 0.0 if suspended[f] else firm_markup(u, v, units, i, cl.direction)
                    labels = period_labels(float(d[i]), S, S_prev, mk, suspended[f])
                    firms_rec[f] = {
                        "e": float(e[i]), "d": float(d[i]), "x": float(x[i]),
                        "u": float(u[idx[0]]), "v": float(v[idx[0]]), "q": float(q_f[i]),
                        "brp": float(st.brp[i]), "bsp": float(bsp_f[i]),
                        "brp_comp": float(st_c.brp[i]), "bsp_comp": float(bsp_c_f[i]),
                        "comp": float(st_c.brp[i] + bsp_c_f[i]),
                        "bsp_costclear": float(bsp_cc_f[i]),
                        "fine": 0.0, "suspended": bool(suspended[f]), "markup": float(mk),
                        **labels,
                    }
                    if len(idx) > 1:
                        firms_rec[f].update(
                            u_blocks=[float(b) for b in u[idx]], v_blocks=[float(b) for b in v[idx]],
                            q_blocks=[float(b) for b in cl.q[idx]],
                        )
                    if m.blocks is not None:
                        # intra-firm self-dealing (ground truth): own BRP aggravates while own BSP marks up
                        firms_rec[f]["self_deal"] = bool(labels["manip"] and labels["markup_flag"])
                order_up = np.argsort(u[eligible], kind="stable")
                order_dn = np.argsort(-v[eligible], kind="stable")
                ue, ve, qe, mwe = u[eligible], v[eligible], cl.q[eligible], units.mw[eligible]
                public = {
                    "t": t, "S": S, "P": cl.price, "direction": cl.direction,
                    "activated_mw": float(cl.q.sum()), "scarcity": cl.scarcity,
                    "merit_up": [
                        {"price": float(ue[j]), "mw": float(mwe[j]), "activated_mw": float(qe[j]) if cl.direction == "short" else 0.0}
                        for j in order_up
                    ],
                    "merit_down": [
                        {"price": float(ve[j]), "mw": float(mwe[j]), "activated_mw": float(qe[j]) if cl.direction == "long" else 0.0}
                        for j in order_dn
                    ],
                }
                rec = {
                    "t": t, "S": S, "S_prev": S_prev, "P": cl.price, "direction": cl.direction, "scarcity": cl.scarcity,
                    "r": r, "S_comp": S_c, "P_comp": cl_c.price, "direction_comp": cl_c.direction,
                    "scarcity_comp": cl_c.scarcity, "activated_mw": float(cl.q.sum()),
                    "activated_mw_comp": float(cl_c.q.sum()),
                    "marginal": self.firms[units.owner[cl.marginal]] if cl.marginal is not None else None,
                    "rest": st.rest, "rest_comp": st_c.rest, "clamped": clamped,
                    "bid_crossed": bool(np.any(v > u)),
                    "firms": firms_rec, "public": public,
                }
                self.records.append(rec)

                events = self.regulator.step(t, self.records, self.channels.public_messages())
                for ev in events:
                    rec["firms"][ev.firm]["fine"] += ev.fine
                    if ev.action == "fine+suspension":
                        suspended_until[ev.firm] = t + cfg.regulator.suspension_periods
                    if ev.notice:
                        self.notices.append({"t": t, "text": ev.notice})
                    evd = ev.to_dict()
                    self.reg_events.append(evd)
                    log.write("regulator", evd)
                rec["public"]["notices"] = [ev.notice for ev in events if ev.notice]

                for msg in self.channels.messages:
                    if msg["t"] == t:
                        log.write("messages", msg)
                log.write("periods", rec)
        finally:
            log.close()

        summary = summarize(
            self.records, self.reg_events, self.channels.messages, self.io_stats, self.agent_notes, cfg,
            wall_time=time.time() - t0,
        )
        return summary
