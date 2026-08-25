"""SmartRoute Cost Tracker — API call counting and token usage statistics.

Tracks:
- AMap API calls (with cache hit/miss)
- DeepSeek API calls (with token usage)
- Route planning requests
- Average latency per endpoint
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CostStats:
    """Aggregated cost statistics."""
    amap_calls: int = 0
    amap_cache_hits: int = 0
    amap_cache_misses: int = 0
    deepseek_calls: int = 0
    deepseek_tokens_input: int = 0
    deepseek_tokens_output: int = 0
    route_plans: int = 0
    adjustments: int = 0
    total_latency_ms: float = 0.0
    request_count: int = 0

    @property
    def amap_cache_hit_rate(self) -> float:
        """Cache hit rate for AMap API."""
        total = self.amap_cache_hits + self.amap_cache_misses
        return self.amap_cache_hits / total if total > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        """Average latency per request."""
        return self.total_latency_ms / self.request_count if self.request_count > 0 else 0.0

    @property
    def deepseek_estimated_cost_usd(self) -> float:
        """Rough cost estimate for DeepSeek API (pricing as of 2026).

        deepseek-chat: $0.27/1M input tokens, $1.10/1M output tokens
        """
        input_cost = self.deepseek_tokens_input * 0.27 / 1_000_000
        output_cost = self.deepseek_tokens_output * 1.10 / 1_000_000
        return input_cost + output_cost

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API response."""
        return {
            "amap_calls": self.amap_calls,
            "amap_cache_hit_rate": round(self.amap_cache_hit_rate, 3),
            "amap_cache_hits": self.amap_cache_hits,
            "amap_cache_misses": self.amap_cache_misses,
            "deepseek_calls": self.deepseek_calls,
            "deepseek_tokens_input": self.deepseek_tokens_input,
            "deepseek_tokens_output": self.deepseek_tokens_output,
            "deepseek_estimated_cost_usd": round(self.deepseek_estimated_cost_usd, 6),
            "route_plans": self.route_plans,
            "adjustments": self.adjustments,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "total_requests": self.request_count,
        }


class CostTracker:
    """Singleton cost tracker for SmartRoute API.

    Usage:
        tracker = get_cost_tracker()
        tracker.record_amap_call(cache_hit=True)
        tracker.record_deepseek_call(input_tokens=100, output_tokens=200)
        tracker.record_request(latency_ms=150)
        stats = tracker.get_stats()
    """

    def __init__(self) -> None:
        self._stats = CostStats()
        self._start_time = time.time()

    def record_amap_call(self, cache_hit: bool) -> None:
        """Record an AMap API call."""
        self._stats.amap_calls += 1
        if cache_hit:
            self._stats.amap_cache_hits += 1
        else:
            self._stats.amap_cache_misses += 1

    def record_deepseek_call(self, input_tokens: int, output_tokens: int) -> None:
        """Record a DeepSeek API call with token usage."""
        self._stats.deepseek_calls += 1
        self._stats.deepseek_tokens_input += input_tokens
        self._stats.deepseek_tokens_output += output_tokens

    def record_route_plan(self) -> None:
        """Record a route planning request."""
        self._stats.route_plans += 1
        self._stats.request_count += 1

    def record_adjustment(self) -> None:
        """Record a route adjustment request."""
        self._stats.adjustments += 1
        self._stats.request_count += 1

    def record_request(self, latency_ms: float) -> None:
        """Record request latency."""
        self._stats.total_latency_ms += latency_ms
        self._stats.request_count += 1

    def get_stats(self) -> CostStats:
        """Get current cost statistics."""
        return self._stats

    def get_uptime_seconds(self) -> float:
        """Get service uptime in seconds."""
        return time.time() - self._start_time

    def reset(self) -> None:
        """Reset all statistics."""
        self._stats = CostStats()
        self._start_time = time.time()


# Singleton instance
_tracker: CostTracker | None = None


def get_cost_tracker() -> CostTracker:
    """Get the global cost tracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker
