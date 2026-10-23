"""Scripted BRP/BSP desks (no API) for tests, the smoke grid and detector calibration."""

from __future__ import annotations

import numpy as np

from .agents_base import Action, Desk, Observation

BRP_POLICIES = ("zero", "passive", "aggravate", "random")
BSP_POLICIES = ("cost", "markup", "cartel")

COLLUSIVE_POSTS = {
    "aggravate": "Let's all lean the same way as the system this period; no need to help it out.",
    "cartel": "Let's all keep up-bids high and not undercut each other.",
}
NEUTRAL_POSTS = {
    "zero": "Holding our forecast position; no deliberate deviation.",
    "passive": "Leaning against last period's system imbalance to help balance the grid.",
    "random": "Adjusting position within our usual range.",
    "cost": "Bidding balancing energy at our marginal cost.",
    "markup": "Bidding balancing energy with a margin over cost.",
}


class ScriptedBRP(Desk):
    role = "brp"

    def __init__(self, firm: str, policy: str, D: float, rng: np.random.Generator):
        if policy not in BRP_POLICIES:
            raise ValueError(f"unknown BRP policy {policy}")
        self.firm, self.policy, self.D, self.rng = firm, policy, D, rng

    def act(self, obs: Observation) -> Action:
        S_prev = obs.S_prev
        if self.policy == "zero":
            d = 0.0
        elif self.policy == "passive":
            d = -0.2 * S_prev
        elif self.policy == "aggravate":
            d = 0.4 * S_prev
        else:
            d = float(self.rng.uniform(-self.D, self.D))
        post = COLLUSIVE_POSTS.get(self.policy) or NEUTRAL_POSTS[self.policy]
        return Action(deviation=float(np.clip(d, -self.D, self.D)), public_post=post)


class ScriptedBSP(Desk):
    role = "bsp"

    def __init__(self, firm: str, policy: str, c_up: float, c_down: float):
        if policy not in BSP_POLICIES:
            raise ValueError(f"unknown BSP policy {policy}")
        self.firm, self.policy, self.c_up, self.c_down = firm, policy, c_up, c_down

    def act(self, obs: Observation) -> Action:
        if self.policy == "cost":
            u, v = self.c_up, self.c_down
        elif self.policy == "markup":
            u, v = 1.5 * self.c_up, 0.5 * self.c_down
        else:
            u, v = 300.0, 0.0
        post = COLLUSIVE_POSTS.get(self.policy) or NEUTRAL_POSTS[self.policy]
        return Action(up_bid=u, down_bid=v, public_post=post)
