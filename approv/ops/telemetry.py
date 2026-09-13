"""Bounded in-process metrics and allowlisted JSON events, without customer content."""
from __future__ import annotations

from collections import Counter, deque
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import logging
import math
from threading import Lock
import time
import uuid

LOG = logging.getLogger("approv.ops")
CURRENT = ContextVar("approv_operation", default=None)
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60)


@dataclass
class Operation:
    kind: str = "verification"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started: float = field(default_factory=time.perf_counter)
    stage: str = "request"
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_usd: float = 0
    unknown_usage_calls: int = 0
    timings: dict = field(default_factory=dict)


def usage_cost(usage, prices):
    if not isinstance(usage, dict):
        return None
    prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens", 0) if isinstance(details, dict) else None
    if (any(type(v) is not int or v < 0 for v in (prompt, completion, cached)) or
            cached > prompt):
        return None
    cost = ((prompt - cached) * prices.input_per_million_usd +
            cached * prices.cached_input_per_million_usd +
            completion * prices.output_per_million_usd) / 1_000_000
    return prompt, completion, cost


class Metrics:
    def __init__(self, window=10000):
        self._lock = Lock()
        self._samples = deque(maxlen=window)
        self._counts = Counter()
        self._tokens = Counter()
        self._buckets = Counter()
        self._sum = 0.0

    def extraction(self, metadata, prices, elapsed, status):
        operation = CURRENT.get() or Operation(kind="readiness")
        counted = usage_cost(metadata.get("usage"), prices)
        operation.calls += 1
        if counted is None:
            operation.unknown_usage_calls += 1
        else:
            operation.input_tokens += counted[0]
            operation.output_tokens += counted[1]
            operation.estimated_usd += counted[2]
        operation.timings["extractor_seconds"] = operation.timings.get("extractor_seconds", 0) + elapsed
        with self._lock:
            self._counts[operation.kind + "_extractor_calls"] += 1
            if counted is None:
                self._counts[operation.kind + "_unknown_usage_calls"] += 1
            else:
                self._tokens[operation.kind + "_input"] += counted[0]
                self._tokens[operation.kind + "_output"] += counted[1]
                self._tokens[operation.kind + "_estimated_usd"] += counted[2]
        LOG.info(json.dumps({"event": "extraction", "operation_id": operation.id,
                            "kind": operation.kind, "status": status,
                            "elapsed_seconds": elapsed,
                            "input_tokens": counted[0] if counted else None,
                            "output_tokens": counted[1] if counted else None,
                            "estimated_usd": counted[2] if counted else None,
                            "price_as_of": prices.as_of}, separators=(",", ":")))

    def finish(self, operation, outcome, status, *, replay=False):
        elapsed = time.perf_counter() - operation.started
        with self._lock:
            self._samples.append(elapsed)
            self._counts["verifications"] += 1
            self._counts[outcome] += 1
            self._counts["replays"] += int(replay)
            self._sum += elapsed
            for bound in BUCKETS:
                self._buckets[bound] += int(elapsed <= bound)
        LOG.info(json.dumps({"event": "verification", "operation_id": operation.id,
                            "outcome": outcome, "http_status": status, "replay": replay,
                            "stage": operation.stage, "elapsed_seconds": elapsed,
                            "stages": operation.timings, "extractor_calls": operation.calls,
                            "input_tokens": operation.input_tokens,
                            "output_tokens": operation.output_tokens,
                            "unknown_usage_calls": operation.unknown_usage_calls,
                            "estimated_usd": None if operation.unknown_usage_calls else operation.estimated_usd},
                           separators=(",", ":")))

    def snapshot(self):
        with self._lock:
            samples = sorted(self._samples)
            def percentile(p):
                return samples[max(0, math.ceil(len(samples) * p) - 1)] if samples else None
            return {"format": "approv-ops-metrics-v1", "call_site": "verify",
                    "window_count": len(samples), "window_capacity": self._samples.maxlen,
                    "p50_seconds": percentile(.5), "p95_seconds": percentile(.95),
                    "counts": dict(self._counts), "tokens_and_estimates": dict(self._tokens)}

    def prometheus(self):
        with self._lock:
            lines = ["# TYPE approv_verification_seconds histogram"]
            for bound in BUCKETS:
                lines.append(f'approv_verification_seconds_bucket{{le="{bound}"}} {self._buckets[bound]}')
            lines.extend([f'approv_verification_seconds_bucket{{le="+Inf"}} {self._counts["verifications"]}',
                          f'approv_verification_seconds_count {self._counts["verifications"]}',
                          f'approv_verification_seconds_sum {self._sum}'])
            for key, value in sorted(self._counts.items()):
                lines.extend([f"# TYPE approv_{key}_total counter", f"approv_{key}_total {value}"])
            for key, value in sorted(self._tokens.items()):
                lines.extend([f"# TYPE approv_{key}_total counter", f"approv_{key}_total {value}"])
            return "\n".join(lines) + "\n"
