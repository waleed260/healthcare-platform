from __future__ import annotations

from typing import Final


ALLOWED_TRANSITIONS: Final[dict[str, set[str]]] = {
    "new": {"contacted", "qualified", "lost", "converted"},
    "contacted": {"qualified", "appointment_booked", "lost", "new", "converted"},
    "qualified": {"appointment_booked", "contacted", "lost", "converted"},
    "appointment_booked": {"visited", "qualified", "lost", "converted"},
    "visited": {"lost", "converted"},
    "converted": set(),
    "lost": {"new", "contacted"},
}


def validate_transition(current: str, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid lead transition: {current} -> {target}")
