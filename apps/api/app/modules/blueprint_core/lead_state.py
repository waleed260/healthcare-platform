from __future__ import annotations

from typing import Final


# Authoritative lead transition matrix. (M) = reachable through the manual PATCH route;
# (E) = event-only (booking service, arrival hook, or the convert endpoint) and rejected on
# the manual route via the LeadUpdate.status literal. See docs/LEADS_IMPLEMENTATION_PLAN.md §6.
ALLOWED_TRANSITIONS: Final[dict[str, set[str]]] = {
    "new": {"contacted", "qualified", "appointment_booked", "lost", "converted"},
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
