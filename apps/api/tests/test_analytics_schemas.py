from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.operations.schemas import ChannelStat, DailyStat, FunnelStep, TopService


class TestDailyStat:
    def test_valid(self):
        stat = DailyStat(date=date(2026, 10, 1), appointments=12, new_patients=3, revenue_minor=150000, no_shows=1)
        assert stat.appointments == 12
        assert stat.date == date(2026, 10, 1)

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            DailyStat(date=date(2026, 10, 1), appointments=0, new_patients=0, revenue_minor=0, no_shows=0, extra=1)


class TestChannelStat:
    def test_valid(self):
        stat = ChannelStat(channel="google", leads=50, converted=10)
        assert stat.channel == "google"
        assert stat.converted == 10

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ChannelStat(channel="google", leads=50, converted=10, extra=1)


class TestFunnelStep:
    def test_valid(self):
        step = FunnelStep(stage="contacted", count=42)
        assert step.stage == "contacted"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            FunnelStep(stage="contacted", count=42, extra=1)


class TestTopService:
    def test_valid(self):
        svc = TopService(name="Dental cleaning", count=30, revenue_minor=900000)
        assert svc.name == "Dental cleaning"
        assert svc.revenue_minor == 900000

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            TopService(name="X", count=1, revenue_minor=100, extra=1)
