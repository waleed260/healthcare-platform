"""Integration tests for analytics endpoints.

These tests require a seeded database with clinic, users, appointments, leads,
services, invoices, and payments. They are skipped by default until the test
database setup includes analytics seed data.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Requires seeded analytics data in test database")


def test_daily_returns_complete_date_range(client, auth_cookie):
    """GET /analytics/daily?range=7d should return exactly 8 rows (today + 7 prior days)."""
    response = client.get("/api/v1/operations/analytics/daily?range=7d", cookies=auth_cookie)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 8


def test_daily_zero_fills_missing_dates(client, auth_cookie):
    """Days with no appointments should still appear with zeroed counts."""
    response = client.get("/api/v1/operations/analytics/daily?range=7d", cookies=auth_cookie)
    data = response.json()["data"]
    for row in data:
        assert row["appointments"] >= 0
        assert row["no_shows"] >= 0


def test_channels_groups_by_source(client, auth_cookie):
    """GET /analytics/channels should group leads by their source field."""
    response = client.get("/api/v1/operations/analytics/channels?range=30d", cookies=auth_cookie)
    assert response.status_code == 200
    data = response.json()["data"]
    channels = [row["channel"] for row in data]
    assert len(channels) == len(set(channels))


def test_funnel_stages_are_ordered(client, auth_cookie):
    """GET /analytics/funnel should return stages in pipeline order."""
    response = client.get("/api/v1/operations/analytics/funnel?range=30d", cookies=auth_cookie)
    assert response.status_code == 200
    stages = [step["stage"] for step in response.json()["data"]]
    assert stages == ["new", "contacted", "qualified", "appointment_booked", "visited", "converted"]


def test_funnel_counts_decrease(client, auth_cookie):
    """Each funnel stage count should be <= the prior stage count."""
    response = client.get("/api/v1/operations/analytics/funnel?range=30d", cookies=auth_cookie)
    data = response.json()["data"]
    for i in range(1, len(data)):
        assert data[i]["count"] <= data[i - 1]["count"]


def test_top_services_limited_to_10(client, auth_cookie):
    """GET /analytics/top-services should return at most 10 services."""
    response = client.get("/api/v1/operations/analytics/top-services?range=90d", cookies=auth_cookie)
    assert response.status_code == 200
    assert len(response.json()["data"]) <= 10
