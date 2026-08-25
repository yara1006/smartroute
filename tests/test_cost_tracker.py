"""Tests for core.cost_tracker — API call counting and cost statistics."""
from __future__ import annotations

from core.cost_tracker import CostTracker, get_cost_tracker


class TestCostTracker:
    """Test cost tracking functionality."""

    def test_initial_stats(self):
        tracker = CostTracker()
        stats = tracker.get_stats()
        assert stats.amap_calls == 0
        assert stats.deepseek_calls == 0
        assert stats.route_plans == 0

    def test_record_amap_call_cache_hit(self):
        tracker = CostTracker()
        tracker.record_amap_call(cache_hit=True)
        stats = tracker.get_stats()
        assert stats.amap_calls == 1
        assert stats.amap_cache_hits == 1
        assert stats.amap_cache_misses == 0
        assert stats.amap_cache_hit_rate == 1.0

    def test_record_amap_call_cache_miss(self):
        tracker = CostTracker()
        tracker.record_amap_call(cache_hit=False)
        stats = tracker.get_stats()
        assert stats.amap_cache_misses == 1
        assert stats.amap_cache_hit_rate == 0.0

    def test_amap_cache_hit_rate_mixed(self):
        tracker = CostTracker()
        tracker.record_amap_call(cache_hit=True)
        tracker.record_amap_call(cache_hit=True)
        tracker.record_amap_call(cache_hit=False)
        stats = tracker.get_stats()
        assert stats.amap_cache_hit_rate == 2/3

    def test_record_deepseek_call(self):
        tracker = CostTracker()
        tracker.record_deepseek_call(input_tokens=100, output_tokens=200)
        stats = tracker.get_stats()
        assert stats.deepseek_calls == 1
        assert stats.deepseek_tokens_input == 100
        assert stats.deepseek_tokens_output == 200

    def test_deepseek_cost_estimate(self):
        tracker = CostTracker()
        # 1M input tokens at $0.27/1M = $0.27
        # 1M output tokens at $1.10/1M = $1.10
        tracker.record_deepseek_call(input_tokens=1_000_000, output_tokens=1_000_000)
        stats = tracker.get_stats()
        assert abs(stats.deepseek_estimated_cost_usd - 1.37) < 0.01

    def test_record_route_plan(self):
        tracker = CostTracker()
        tracker.record_route_plan()
        stats = tracker.get_stats()
        assert stats.route_plans == 1
        assert stats.request_count == 1

    def test_record_adjustment(self):
        tracker = CostTracker()
        tracker.record_adjustment()
        stats = tracker.get_stats()
        assert stats.adjustments == 1

    def test_record_request_latency(self):
        tracker = CostTracker()
        tracker.record_request(latency_ms=150.0)
        stats = tracker.get_stats()
        assert stats.avg_latency_ms == 150.0

    def test_avg_latency_multiple_requests(self):
        tracker = CostTracker()
        tracker.record_request(latency_ms=100.0)
        tracker.record_request(latency_ms=200.0)
        stats = tracker.get_stats()
        assert stats.avg_latency_ms == 150.0

    def test_to_dict(self):
        tracker = CostTracker()
        tracker.record_amap_call(cache_hit=True)
        tracker.record_deepseek_call(input_tokens=50, output_tokens=100)
        tracker.record_route_plan()
        stats = tracker.get_stats()
        d = stats.to_dict()
        assert "amap_calls" in d
        assert "deepseek_estimated_cost_usd" in d
        assert "avg_latency_ms" in d

    def test_reset(self):
        tracker = CostTracker()
        tracker.record_amap_call(cache_hit=True)
        tracker.reset()
        stats = tracker.get_stats()
        assert stats.amap_calls == 0

    def test_singleton(self):
        t1 = get_cost_tracker()
        t2 = get_cost_tracker()
        assert t1 is t2

    def test_uptime(self):
        tracker = CostTracker()
        uptime = tracker.get_uptime_seconds()
        assert uptime >= 0
