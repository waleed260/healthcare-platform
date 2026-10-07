import pytest
from fastapi import HTTPException

from app.modules.operations.routes import _parse_range


class TestParseRange:
    def test_7d(self):
        assert _parse_range("7d") == 7

    def test_30d(self):
        assert _parse_range("30d") == 30

    def test_90d(self):
        assert _parse_range("90d") == 90

    def test_invalid_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_range("14d")
        assert exc_info.value.status_code == 400

    def test_empty_raises(self):
        with pytest.raises(HTTPException):
            _parse_range("")

    def test_numeric_only_raises(self):
        with pytest.raises(HTTPException):
            _parse_range("30")
