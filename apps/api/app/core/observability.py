from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class RequestMetrics:
    """Small bounded metrics collector; labels never contain request values or IDs."""

    def __init__(self, sample_limit: int = 4096) -> None:
        self._lock = Lock()
        self._counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self._latencies: dict[tuple[str, str], deque[float]] = defaultdict(lambda: deque(maxlen=sample_limit))

    def observe(self, method: str, route: str, status_code: int, elapsed_ms: float) -> None:
        key = (method, route, status_code)
        latency_key = (method, route)
        with self._lock:
            self._counts[key] += 1
            self._latencies[latency_key].append(elapsed_ms)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            counts = [{"method": method, "route": route, "status_code": status, "count": count} for (method, route, status), count in sorted(self._counts.items())]
            latency = []
            for (method, route), values in sorted(self._latencies.items()):
                ordered = sorted(values)
                if not ordered:
                    continue
                def percentile(percent: float) -> float:
                    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percent)))
                    return round(ordered[index], 2)
                latency.append({"method": method, "route": route, "sample_count": len(ordered), "p50_ms": percentile(.50), "p95_ms": percentile(.95), "p99_ms": percentile(.99)})
            return {"requests": counts, "latency": latency}


request_metrics = RequestMetrics()


def timer() -> float:
    return monotonic()
