"""Pure provider revenue and commission calculations (cash basis, blueprint §12.4)."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping
from uuid import UUID

Unassigned = None


def split_amount(amount: int, weights: Mapping[UUID | None, int]) -> dict[UUID | None, int]:
    """Split ``amount`` across weights proportionally; integer-exact with the remainder going to the largest weight."""
    total = sum(weights.values())
    if amount <= 0 or total <= 0:
        return {key: 0 for key in weights}
    shares = {key: amount * weight // total for key, weight in weights.items()}
    remainder = amount - sum(shares.values())
    if remainder:
        largest = max(weights, key=lambda key: (weights[key], str(key)))
        shares[largest] += remainder
    return shares


def provider_revenue(allocations: Iterable[tuple[UUID, int]], line_totals: Mapping[UUID, Mapping[UUID | None, int]]) -> dict[UUID | None, int]:
    """Revenue per provider from payment allocations: each paid amount is shared by that invoice's line totals.

    ``allocations`` are (invoice_id, amount_minor) rows; ``line_totals`` maps invoice_id -> {provider_id|None: sum of line totals}.
    Lines without a provider accumulate under ``None``.
    """
    revenue: dict[UUID | None, int] = defaultdict(int)
    for invoice_id, amount in allocations:
        weights = line_totals.get(invoice_id)
        if not weights:
            continue
        for provider, share in split_amount(amount, weights).items():
            revenue[provider] += share
    return dict(revenue)


def commission_minor(revenue_minor: int, percent_bp: int | None, active: bool = True) -> int:
    if not active or not percent_bp or revenue_minor <= 0:
        return 0
    return revenue_minor * percent_bp // 10_000
