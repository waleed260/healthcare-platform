#!/usr/bin/env python3
"""Run a bounded, synthetic HTTP pilot-load profile.

This tool deliberately has no application/database access and sends no request
body unless the operator supplies one in a request-plan JSON file. It is safe
to run against a local or staging deployment when the synthetic-load guard is
explicitly enabled.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


THRESHOLDS_MS = {
    "api-list": 500.0,
    "availability": 800.0,
    "booking": 1500.0,
    "dashboard": 2500.0,
}


@dataclass(frozen=True)
class RequestSpec:
    method: str
    path: str
    body: bytes | None = None
    headers: dict[str, str] | None = None
    weight: int = 1


@dataclass(frozen=True)
class Sample:
    latency_ms: float
    status: int
    error: str | None = None


def percentile(values: list[float], percentile_rank: float) -> float:
    """Return an interpolated percentile without requiring a third-party lib."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile_rank / 100
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def load_request_plan(path: Path | None) -> list[RequestSpec]:
    if path is None:
        return [RequestSpec("GET", "/health/live")]
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("request plan must be a non-empty JSON array")
    plan: list[RequestSpec] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("each request plan entry needs a string path")
        body = item.get("body")
        if body is not None and not isinstance(body, (dict, list, str)):
            raise ValueError("request body must be an object, array, or string")
        encoded = None if body is None else (
            body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
        )
        weight = item.get("weight", 1)
        if not isinstance(weight, int) or weight < 1:
            raise ValueError("request weight must be a positive integer")
        plan.append(RequestSpec(
            method=str(item.get("method", "GET")).upper(),
            path=item["path"],
            body=encoded,
            headers=item.get("headers") if isinstance(item.get("headers"), dict) else None,
            weight=weight,
        ))
    return plan


def choose_request(plan: list[RequestSpec]) -> RequestSpec:
    return random.choices(plan, weights=[item.weight for item in plan], k=1)[0]


def load_session_cookies(path: Path | None, session_count: int) -> list[str]:
    """Load short-lived synthetic session cookies without including them in output."""
    if session_count <= 0:
        raise ValueError("session count must be positive")
    if path is not None:
        cookies = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(cookies) != session_count:
            raise ValueError("session cookie file must contain exactly --sessions non-empty lines")
        return cookies
    cookie = os.environ.get("LOAD_COOKIE", "").strip()
    return [cookie] if cookie else []


def request_once(base_url: str, spec: RequestSpec, timeout: float, common_headers: dict[str, str], session_cookie: str | None = None) -> Sample:
    url = f"{base_url.rstrip('/')}/{spec.path.lstrip('/')}"
    headers = {**common_headers, **(spec.headers or {})}
    if session_cookie:
        headers["Cookie"] = session_cookie
    if spec.body is not None:
        headers.setdefault("Content-Type", "application/json")
    started = time.perf_counter()
    try:
        with urlopen(Request(url, data=spec.body, headers=headers, method=spec.method), timeout=timeout) as response:
            response.read(1024)
            status = response.status
            error = None if 200 <= status < 400 else f"HTTP {status}"
    except HTTPError as exc:
        status = exc.code
        error = f"HTTP {exc.code}"
    except (TimeoutError, URLError, OSError) as exc:
        status = 0
        error = type(exc).__name__
    return Sample((time.perf_counter() - started) * 1000, status, error)


def summarize(samples: list[Sample], elapsed_s: float, configured_rate: float) -> dict[str, Any]:
    latencies = [sample.latency_ms for sample in samples]
    statuses: dict[str, int] = {}
    for sample in samples:
        key = str(sample.status)
        statuses[key] = statuses.get(key, 0) + 1
    errors = sum(sample.error is not None for sample in samples)
    return {
        "requests": len(samples),
        "errors": errors,
        "error_rate": round(errors / len(samples), 4) if samples else 0.0,
        "configured_rate_per_second": configured_rate,
        "observed_rate_per_second": round(len(samples) / elapsed_s, 2) if elapsed_s else 0.0,
        "elapsed_seconds": round(elapsed_s, 3),
        "latency_ms": {
            "p50": round(percentile(latencies, 50), 2),
            "p95": round(percentile(latencies, 95), 2),
            "p99": round(percentile(latencies, 99), 2),
            "max": round(max(latencies), 2) if latencies else 0.0,
        },
        "status_counts": statuses,
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if not args.dry_run and os.environ.get("ALLOW_SYNTHETIC_LOAD") != "YES":
        raise SystemExit("refusing live load: set ALLOW_SYNTHETIC_LOAD=YES")
    if args.duration <= 0 or args.rate <= 0 or args.concurrency <= 0 or args.max_errors < 0:
        raise SystemExit("duration, rate, and concurrency must be positive")
    plan = load_request_plan(args.request_plan)
    session_cookies = load_session_cookies(args.session_cookie_file, args.sessions)
    configuration = {
        "profile": args.profile,
        "base_url": args.base_url,
        "duration_seconds": args.duration,
        "rate_per_second": args.rate,
        "concurrency": args.concurrency,
        "session_count": args.sessions,
        "authenticated_session_count": len(session_cookies),
        "request_plan": [spec.path for spec in plan],
        "synthetic_guard": os.environ.get("ALLOW_SYNTHETIC_LOAD") == "YES",
    }
    if args.dry_run:
        return {"mode": "dry-run", "configuration": configuration}, 0

    common_headers = {"User-Agent": "healthcare-synthetic-load/1.0", "X-Synthetic-Load": "true"}
    if os.environ.get("LOAD_AUTHORIZATION"):
        common_headers["Authorization"] = os.environ["LOAD_AUTHORIZATION"]
    if os.environ.get("LOAD_COOKIE") and not session_cookies:
        common_headers["Cookie"] = os.environ["LOAD_COOKIE"]
    samples: list[Sample] = []
    lock = Lock()
    deadline = time.monotonic() + args.duration
    started = time.perf_counter()
    session_index = 0
    session_lock = Lock()

    def submit_at(executor: ThreadPoolExecutor) -> None:
        with lock:
            if time.monotonic() >= deadline:
                return
        nonlocal session_index
        with session_lock:
            session_cookie = session_cookies[session_index % len(session_cookies)] if session_cookies else None
            session_index += 1
        future = executor.submit(request_once, args.base_url, choose_request(plan), args.timeout, common_headers, session_cookie)
        with lock:
            future.add_done_callback(lambda completed: samples.append(completed.result()))

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        interval = 1 / args.rate
        next_request = time.monotonic()
        while time.monotonic() < deadline:
            submit_at(executor)
            next_request += interval
            time.sleep(max(0, next_request - time.monotonic()))
        executor.shutdown(wait=True)
    result = {"configuration": configuration, **summarize(samples, time.perf_counter() - started, args.rate)}
    threshold = args.max_p95_ms if args.max_p95_ms is not None else THRESHOLDS_MS[args.profile]
    failed = result["latency_ms"]["p95"] > threshold or result["errors"] > args.max_errors
    result["acceptance"] = {"p95_threshold_ms": threshold, "max_errors": args.max_errors, "passed": not failed}
    return result, 1 if failed else 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--base-url", default="http://127.0.0.1:8000")
    result.add_argument("--profile", choices=sorted(THRESHOLDS_MS), default="api-list")
    result.add_argument("--request-plan", type=Path, help="JSON array of synthetic request definitions")
    result.add_argument("--duration", type=float, default=60)
    result.add_argument("--rate", type=float, default=20)
    result.add_argument("--concurrency", type=int, default=50)
    result.add_argument("--sessions", type=int, default=50, help="number of synthetic sessions represented by the profile")
    result.add_argument("--session-cookie-file", type=Path, help="file containing one short-lived synthetic Cookie header per session")
    result.add_argument("--timeout", type=float, default=10)
    result.add_argument("--max-p95-ms", type=float)
    result.add_argument("--max-errors", type=int, default=0)
    result.add_argument("--dry-run", action="store_true")
    return result


if __name__ == "__main__":
    try:
        output, exit_code = run(parser().parse_args())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"load profile configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(output, indent=2, sort_keys=True))
    raise SystemExit(exit_code)
