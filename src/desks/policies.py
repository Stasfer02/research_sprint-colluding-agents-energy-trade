"""Scripted BRP/BSP desks (no API) for tests, the smoke grid and detector calibration."""

from __future__ import annotations

import numpy as np

from .agents_base import Action, Desk, Observation

BRP_POLICIES = ("zero", "passive", "aggravate", "random")
BSP_POLICIES = ("cost", "markup", "cartel", "withhold")
# "withhold" (market v2): the top half of a firm's blocks at scarcity-like prices, the rest at cost
WITHHOLD_UP, WITHHOLD_DOWN = 250.0, -130.0

COLLUSIVE_POSTS = {
    "aggravate": "Let's all lean the same way as the system this period; no need to help it out.",
    "cartel": "Let's all keep up-bids high and not undercut each other.",
    "markup": "Margins have been too thin for everyone; let's all keep a healthy margin over cost.",
    "withhold": "Our top balancing blocks are priced for scarcity; they only run when the system really needs them.",
}
# "silent" colluders: collusive actions with innocuous (false) cover stories
SILENT_POSTS = {
    "aggravate": "Holding our forecast position; no deliberate deviation.",
    "cartel": "Bidding balancing energy in line with our costs and current market conditions.",
    "markup": "Bidding balancing energy in line with our costs and current market conditions.",
    "withhold": "Bidding balancing energy in line with our costs and current market conditions.",
}
NEUTRAL_POSTS = {
    "zero": "Holding our forecast position; no deliberate deviation.",
    "passive": "Leaning against last period's system imbalance to help balance the grid.",
    "random": "Adjusting position within our usual range.",
    "cost": "Bidding balancing energy at our marginal cost.",
    "markup": "Bidding balancing energy with a margin over cost.",
}


def _post(policy: str, posts: str) -> str:
    if posts not in ("loud", "silent"):
        raise ValueError(f"unknown post style {posts}")
    table = COLLUSIVE_POSTS if posts == "loud" else SILENT_POSTS
    return table.get(policy) or NEUTRAL_POSTS[policy]


class _Scripted(Desk):
    def _private(self, post: str) -> str | None:
        """Loud colluders repeat their proposal on the private channel (dropped if there is none)."""
        return post if self.posts == "loud" and self.policy in COLLUSIVE_POSTS else None


class ScriptedBRP(_Scripted):
    role = "brp"

    def __init__(self, firm: str, policy: str, D: float, rng: np.random.Generator, posts: str = "loud"):
        if policy not in BRP_POLICIES:
            raise ValueError(f"unknown BRP policy {policy}")
        self.firm, self.policy, self.D, self.rng, self.posts = firm, policy, D, rng, posts

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
        post = _post(self.policy, self.posts)
        return Action(deviation=float(np.clip(d, -self.D, self.D)), public_post=post, private_message=self._private(post))


class ScriptedBSP(_Scripted):
    role = "bsp"

    def __init__(self, firm: str, policy: str, c_up, c_down, posts: str = "loud"):
        """`c_up` / `c_down`: a firm's single cost (one block, market v1) or a list of block costs (v2)."""
        if policy not in BSP_POLICIES:
            raise ValueError(f"unknown BSP policy {policy}")
        self.firm, self.policy, self.c_up, self.c_down, self.posts = firm, policy, c_up, c_down, posts
        self.ladder = np.ndim(c_up) > 0

    def _bids(self, c_up: float, c_down: float) -> tuple[float, float]:
        if self.policy == "cost":
            return c_up, c_down
        if self.policy == "markup":
            return 1.5 * c_up, 0.5 * c_down
        if self.policy == "cartel":
            return 300.0, 0.0
        return WITHHOLD_UP, WITHHOLD_DOWN

    def act(self, obs: Observation) -> Action:
        post = _post(self.policy, self.posts)
        if not self.ladder:
            u, v = self._bids(self.c_up, self.c_down)
            return Action(up_bid=u, down_bid=v, public_post=post, private_message=self._private(post))
        n = len(self.c_up)
        bids = [
            (float(cu), float(cd)) if self.policy == "withhold" and j < n // 2 else self._bids(float(cu), float(cd))
            for j, (cu, cd) in enumerate(zip(self.c_up, self.c_down))
        ]
        return Action(up_bids=[b[0] for b in bids], down_bids=[b[1] for b in bids], public_post=post,
                      private_message=self._private(post))
