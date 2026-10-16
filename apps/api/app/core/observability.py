from __future__ import annotations

from collections import defaultdict, deque
import json
import logging
from threading import Lock
from time import monotonic
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Emit bounded structured logs without request bodies or credential data."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "route", "status_code", "elapsed_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_logging() -> None:
    """Configure one redacted JSON stream for platform logs."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def redact_sentry_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    """Remove request data and identity material before an event leaves the API."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "headers", "env", "query_string"):
            request.pop(key, None)
        request.pop("user", None)
    event.pop("user", None)
    event.pop("breadcrumbs", None)
    extra = event.get("extra")
    if isinstance(extra, dict):
        event["extra"] = {key: value for key, value in extra.items() if key not in {"body", "token", "password", "authorization"}}
    return event


def initialize_sentry(settings: Any) -> None:
    """Enable Sentry only when a provider DSN is explicitly configured."""
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        send_default_pii=False,
        before_send=redact_sentry_event,
    )


class RequestMetrics:
    """Small bounded metrics collector; labels never contain request values or IDs.

    observe() is lock-free (deque.append is thread-safe in CPython) so the async
    middleware hot path never blocks. Aggregation happens in snapshot() only.
    """

    def __init__(self, sample_limit: int = 8192) -> None:
        self._lock = Lock()
        self._samples: deque[tuple[str, str, int, float]] = deque(maxlen=sample_limit)

    def observe(self, method: str, route: str, status_code: int, elapsed_ms: float) -> None:
        self._samples.append((method, route, status_code, elapsed_ms))

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            samples = list(self._samples)
        counts: dict[tuple[str, str, int], int] = defaultdict(int)
        latencies: dict[tuple[str, str], list[float]] = defaultdict(list)
        for method, route, status_code, elapsed_ms in samples:
            counts[(method, route, status_code)] += 1
            latencies[(method, route)].append(elapsed_ms)
        count_list = [{"method": m, "route": r, "status_code": s, "count": c} for (m, r, s), c in sorted(counts.items())]
        latency_list = []
        for (method, route), values in sorted(latencies.items()):
            ordered = sorted(values)
            if not ordered:
                continue
            def percentile(percent: float, data: list[float] = ordered) -> float:
                index = min(len(data) - 1, max(0, round((len(data) - 1) * percent)))
                return round(data[index], 2)
            latency_list.append({"method": method, "route": route, "sample_count": len(ordered), "p50_ms": percentile(.50), "p95_ms": percentile(.95), "p99_ms": percentile(.99)})
        return {"requests": count_list, "latency": latency_list}


request_metrics = RequestMetrics()


def timer() -> float:
    return monotonic()
