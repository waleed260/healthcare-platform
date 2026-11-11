from __future__ import annotations

from typing import Final


ALLOWED_TRANSITIONS: Final[dict[str, set[str]]] = {
    "new": {"contacted", "qualified", "lost"},
    "contacted": {"qualified", "appointment_booked", "lost", "new"},
    "qualified": {"appointment_booked", "contacted", "lost"},
    "appointment_booked": {"visited", "qualified", "lost"},
    "visited": {"lost"},
    "converted": set(),
    "lost": {"new", "contacted"},
}


def validate_transition(current: str, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid lead transition: {current} -> {target}")
