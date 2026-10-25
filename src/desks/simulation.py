"""The period loop: build each desk's observation, collect actions, clear and settle the market, log everything."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from . import FIRMS
from .agents import Action, LLMDesk, Observation
from .config import RunConfig
from .market import clamp_bids, clear, settle

DESK_NAMES = {"brp": "trading desk", "bsp": "balancing desk"}


def make_streams(seed: int, T: int, n: int, sigma_f: float, sigma_r: float, rho: float):
    """Noise drawn up front from separate seeded streams, so agent behaviour never changes the noise path.

    Returns forecast errors e (T x n), the rest-of-market imbalance r (AR(1), length T) and tie-break keys (T x n).
    """
    noise_ss, tie_ss = np.random.SeedSequence(seed).spawn(4)[:2]  # streams 3-4 were used by removed features
    rng_noise = np.random.default_rng(noise_ss)
    e = rng_noise.normal(0.0, sigma_f, (T, n))
    eps = rng_noise.normal(0.0, sigma_r, T)
    r = np.zeros(T)
    prev = 0.0
    for t in range(T):
        prev = rho * prev + eps[t]
        r[t] = prev
    tie = np.random.default_rng(tie_ss).random((T, n))
    return e, r, tie


class Simulation:
    def __init__(self, cfg: RunConfig, desks: dict[str, dict[str, LLMDesk]], run_dir: Path | None = None):
        self.cfg = cfg
        m = cfg.market
        self.n = len(FIRMS)
        self.e, self.r, self.tie = make_streams(cfg.seed, m.T, self.n, m.sigma_f, m.sigma_r, m.rho)
        self.desks = desks
        self.run_dir = run_dir
        self.show_fines = cfg.regulator.enforcement == "stated"
        self.records: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []  # public board; posts written in t are shown from t+1
        self.io_stats: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ observations
    def _board(self, t: int) -> list[dict[str, Any]]:
        lo = t - self.cfg.channel.board_periods
        return [msg for msg in self.messages if lo <= msg["t"] < t]

    def _observation(self, firm: str, role: str, t: int) -> Observation:
        recent = self.records[-self.cfg.agents.history_window:]
        own = []
        for rec in recent:
            f = rec["firms"][firm]
            row: dict[str, Any] = {"t": rec["t"], "fine": 0.0}
            if role == "brp":
                row.update(deviation_mw=f["d"], position_mw=f["x"], brp_pnl=f["brp"])
            else:
                row.update(up_bid=f["u"], down_bid=f["v"], activated_mw=f["q"], bsp_pnl=f["bsp"])
            own.append(row)
        brp = sum(rec["firms"][firm]["brp"] for rec in self.records)
        bsp = sum(rec["firms"][firm]["bsp"] for rec in self.records)
        return Observation(
            firm=firm, role=role, t=t, T=self.cfg.market.T,
            public_history=[rec["public"] for rec in recent], own_history=own,
            cum_profit=brp + bsp, profit_label=f"Firm {firm} total profit (both desks{', after fines' if self.show_fines else ''})",
            board=self._board(t), brp_profit=brp, bsp_profit=bsp, show_fines=self.show_fines,
        )

    def _collect_actions(self, t: int) -> dict[tuple[str, str], Action]:
        jobs = [(firm, role, desk) for firm in FIRMS for role, desk in self.desks[firm].items()]
        with ThreadPoolExecutor(max_workers=self.cfg.llm.desk_workers) as pool:
            results = list(pool.map(lambda job: job[2].act(self._observation(job[0], job[1], t)), jobs))
        return {(firm, role): res for (firm, role, _), res in zip(jobs, results)}

    # ------------------------------------------------------------------ main loop
    def run(self) -> dict[str, Any]:
        cfg, m = self.cfg, self.cfg.market
        logs = {}
        if self.run_dir is not None:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            (self.run_dir / "config.json").write_text(json.dumps(cfg.to_dict(), indent=2, default=_json_default))
            logs = {name: open(self.run_dir / f"{name}.jsonl", "w") for name in ("periods", "agent_io", "messages")}

        def log(name: str, obj: dict[str, Any]) -> None:
            if name in logs:
                logs[name].write(json.dumps(obj, default=_json_default) + "\n")
                logs[name].flush()

        t0 = time.time()
        try:
            for t in range(1, m.T + 1):
                actions = self._collect_actions(t)
                d = np.zeros(self.n)
                u = np.asarray(m.c_up, dtype=float).copy()
                v = np.asarray(m.c_down, dtype=float).copy()
                for i, f in enumerate(FIRMS):
                    for role in ("brp", "bsp"):
                        a = actions[(f, role)]
                        if role == "brp" and a.deviation is not None:
                            d[i] = a.deviation
                        if role == "bsp":
                            u[i] = a.up_bid if a.up_bid is not None else u[i]
                            v[i] = a.down_bid if a.down_bid is not None else v[i]
                        if a.public_post and a.public_post.strip():
                            self.messages.append({
                                "t": t, "channel": "public", "author_firm": f, "desk": role,
                                "author": f"Firm {f} — {DESK_NAMES[role]}", "text": a.public_post.strip()[: cfg.channel.max_chars],
                            })
                        for entry in a.io:
                            log("agent_io", {"t": t, "firm": f, "desk": role, **entry})
                            if "input_tokens" in entry:
                                self.io_stats.append(entry)
                        if a.io and not a.parse_ok:
                            self.io_stats.append({"parse_fail": True})
                d = np.clip(d, -m.D, m.D)
                u, v, clamped = clamp_bids(u, v, m)
                self.records.append(self._record(t, d, u, v, clamped))
                for msg in self.messages:
                    if msg["t"] == t:
                        log("messages", msg)
                log("periods", self.records[-1])
        finally:
            for fh in logs.values():
                fh.close()
        return self._summary(time.time() - t0)

    def _summary(self, wall_time: float) -> dict[str, Any]:
        """summary.json: run identity and LLM usage."""
        cfg = self.cfg
        calls = [s for s in self.io_stats if "input_tokens" in s]
        failures = sum(1 for s in self.io_stats if s.get("parse_fail"))
        n_decisions = len(self.records) * 2 * len(FIRMS)
        return {
            "grid": cfg.grid, "cell_id": cfg.cell_id, "seed": cfg.seed, "complete": True, "periods": len(self.records),
            "model": cfg.llm.model, "enforcement": cfg.regulator.enforcement, "llm_calls": len(calls),
            "parse_failures": failures, "parse_failure_rate": failures / n_decisions if n_decisions else 0.0,
            "tokens_in": int(sum(s["input_tokens"] for s in calls)), "tokens_out": int(sum(s["output_tokens"] for s in calls)),
            "cost_usd": float(sum(s.get("cost", 0.0) for s in calls)), "wall_time_s": float(wall_time),
        }

    def _record(self, t: int, d: np.ndarray, u: np.ndarray, v: np.ndarray, clamped: bool) -> dict[str, Any]:
        """Clear and settle period t."""
        m = self.cfg.market
        k = t - 1
        e, r, keys = self.e[k], float(self.r[k]), self.tie[k]
        x = e + d
        S = float(x.sum() + r)
        cl = clear(S, u, v, keys, m)
        st = settle(x, r, cl, m)
        firms = {
            f: {"e": float(e[i]), "d": float(d[i]), "x": float(x[i]), "u": float(u[i]), "v": float(v[i]),
                "q": float(cl.q[i]), "brp": float(st.brp[i]), "bsp": float(st.bsp[i])}
            for i, f in enumerate(FIRMS)
        }
        merit = lambda bids, side, order: [  # noqa: E731
            {"price": float(bids[j]), "mw": float(m.K), "activated_mw": float(cl.q[j]) if cl.direction == side else 0.0}
            for j in order
        ]
        public = {  # what every desk sees about period t: no firm names in the merit order
            "t": t, "S": S, "P": cl.price, "direction": cl.direction, "activated_mw": float(cl.q.sum()),
            "scarcity": cl.scarcity,
            "merit_up": merit(u, "short", np.argsort(u, kind="stable")),
            "merit_down": merit(v, "long", np.argsort(-v, kind="stable")),
        }
        return {
            "t": t, "S": S, "P": cl.price, "direction": cl.direction, "scarcity": cl.scarcity, "r": r,
            "activated_mw": float(cl.q.sum()), "marginal": FIRMS[cl.marginal] if cl.marginal is not None else None,
            "rest": st.rest, "clamped": clamped, "firms": firms, "public": public,
        }


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))
