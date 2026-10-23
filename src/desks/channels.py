"""Public board and "private" channel. Messages written in t are delivered from t+1."""

from __future__ import annotations

from typing import Any

PUBLIC, PRIVATE = "public", "private"
DESK_NAMES = {"brp": "trading desk", "bsp": "balancing desk", "integrated": "firm desk"}


def author_label(firm: str, desk: str) -> str:
    return f"Firm {firm} — {DESK_NAMES[desk]}"


class Channels:
    def __init__(self, channel: str, board_periods: int = 2, max_chars: int = 300):
        if channel not in ("none", "public", "public_private"):
            raise ValueError(f"unknown channel {channel}")
        self.channel = channel
        self.board_periods = board_periods
        self.max_chars = max_chars
        self.messages: list[dict[str, Any]] = []

    @property
    def has_public(self) -> bool:
        return self.channel in ("public", "public_private")

    @property
    def has_private(self) -> bool:
        return self.channel == "public_private"

    def post(self, t: int, firm: str, desk: str, public: str | None, private: str | None) -> None:
        for kind, text, allowed in ((PUBLIC, public, self.has_public), (PRIVATE, private, self.has_private)):
            if allowed and text and str(text).strip():
                self.messages.append({
                    "t": t, "channel": kind, "author_firm": firm, "desk": desk,
                    "author": author_label(firm, desk), "text": str(text).strip()[: self.max_chars],
                })

    def _recent(self, t: int, kind: str) -> list[dict[str, Any]]:
        lo = t - self.board_periods
        return [m for m in self.messages if m["channel"] == kind and lo <= m["t"] < t]

    def board(self, t: int) -> list[dict[str, Any]]:
        return self._recent(t, PUBLIC) if self.has_public else []

    def private(self, t: int) -> list[dict[str, Any]]:
        return self._recent(t, PRIVATE) if self.has_private else []

    def public_messages(self) -> list[dict[str, Any]]:
        return [m for m in self.messages if m["channel"] == PUBLIC]
