import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from infra.performance.load_profile import Sample, load_session_cookies, percentile, summarize


def test_percentile_interpolates_and_empty_is_zero():
    assert percentile([], 95) == 0
    assert percentile([10, 20, 30, 40], 50) == 25
    assert percentile([10, 20, 30, 40], 95) == 38.5


def test_summary_counts_errors_and_rates():
    result = summarize(
        [Sample(10, 200), Sample(20, 200), Sample(30, 503, "HTTP 503")],
        elapsed_s=1.0,
        configured_rate=20,
    )
    assert result["requests"] == 3
    assert result["errors"] == 1
    assert result["status_counts"] == {"200": 2, "503": 1}
    assert result["latency_ms"]["p95"] == 29


def test_session_cookie_file_requires_exact_synthetic_session_count(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("healthcare_session=one\nhealthcare_session=two\n", encoding="utf-8")
    assert load_session_cookies(cookie_file, 2) == ["healthcare_session=one", "healthcare_session=two"]


def test_session_cookie_file_count_mismatch_fails_closed(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("healthcare_session=one\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly --sessions"):
        load_session_cookies(cookie_file, 2)
