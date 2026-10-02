from uuid import uuid4

from app.main import app
from app.modules.finance.commissions import commission_minor, provider_revenue, split_amount

A, B = uuid4(), uuid4()


def test_split_is_exact_and_proportional() -> None:
    assert split_amount(100, {A: 3, B: 1}) == {A: 75, B: 25}
    shares = split_amount(101, {A: 1, B: 1, None: 1})
    assert sum(shares.values()) == 101
    assert split_amount(0, {A: 1}) == {A: 0}
    assert split_amount(50, {A: 0}) == {A: 0}


def test_revenue_follows_payments_and_line_shares() -> None:
    inv1, inv2 = uuid4(), uuid4()
    revenue = provider_revenue(
        [(inv1, 500), (inv2, 1000), (uuid4(), 999)],  # last invoice has no lines: ignored
        {inv1: {A: 600, B: 400}, inv2: {A: 100, None: 300}},
    )
    assert revenue[A] == 300 + 250 and revenue[B] == 200 and revenue[None] == 750
    assert sum(revenue.values()) == 1500


def test_commission_rules() -> None:
    assert commission_minor(100_000, 2500) == 25_000
    assert commission_minor(100_000, 2500, active=False) == 0
    assert commission_minor(100_000, None) == 0 and commission_minor(-5, 1000) == 0
    assert commission_minor(999, 1) == 0


def test_routes_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert {"/api/v1/finance/commission-rules", "/api/v1/finance/commission-rules/{doctor_id}", "/api/v1/finance/provider-revenue"} <= paths
