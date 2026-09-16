from __future__ import annotations

from typing import Final


ALLOWED_TRANSITIONS: Final[dict[str, set[str]]] = {
    "requested": {"confirmed", "cancelled"},
    "confirmed": {"arrived", "rescheduled", "cancelled", "no_show"},
    "arrived": {"waiting", "cancelled"},
    "waiting": {"in_consultation", "cancelled"},
    "in_consultation": {"completed"},
    "completed": set(),
    "rescheduled": set(),
    "cancelled": set(),
    "no_show": set(),
}


def validate_transition(current: str, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid appointment transition: {current} -> {target}")
