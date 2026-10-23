from __future__ import annotations

from desks import FIRMS


def firm_rec(**kw):
    base = {
        "e": 0.0, "d": 0.0, "x": 0.0, "u": 70.0, "v": 55.0, "q": 0.0,
        "brp": 0.0, "bsp": 0.0, "brp_comp": 0.0, "bsp_comp": 0.0, "comp": 0.0, "bsp_costclear": 0.0,
        "fine": 0.0, "suspended": False, "markup": 0.0, "manip": False, "markup_flag": False, "passive": False,
    }
    base.update(kw)
    return base


def period(t, S, S_prev=0.0, **firm_overrides):
    """Period record with default (benchmark-like) firms; firm_overrides maps firm -> dict."""
    return {
        "t": t, "S": S, "S_prev": S_prev, "P": 60.0, "direction": "short" if S < -1 else "long" if S > 1 else "balanced",
        "firms": {f: firm_rec(**firm_overrides.get(f, {})) for f in FIRMS},
    }
