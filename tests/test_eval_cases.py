"""Tests for SmartRoute Eval framework — 20 eval cases across 5 metrics."""
from __future__ import annotations

import pytest

from core.eval import EVAL_CASES, EvalMetric, eval_summary, run_eval_case


class TestEvalCases:
    """Validate the 20 eval cases are well-formed."""

    def test_total_case_count(self):
        assert len(EVAL_CASES) == 20

    def test_case_ids_unique(self):
        ids = [c.id for c in EVAL_CASES]
        assert len(ids) == len(set(ids))

    def test_categories_covered(self):
        categories = {c.category for c in EVAL_CASES}
        expected = {"regular", "budget", "preference", "change", "safety"}
        assert categories == expected

    def test_four_cases_per_category(self):
        from collections import Counter
        counts = Counter(c.category for c in EVAL_CASES)
        for cat in ["regular", "budget", "preference", "change", "safety"]:
            assert counts[cat] == 4, f"{cat} has {counts[cat]} cases, expected 4"

    def test_all_metrics_represented(self):
        metrics = {c.metric for c in EVAL_CASES}
        assert metrics == set(EvalMetric)

    def test_each_case_has_required_fields(self):
        for case in EVAL_CASES:
            assert case.id
            assert case.category
            assert case.description
            assert case.input_query
            assert case.expected_behavior
            assert case.metric


class TestEvalMetrics:
    """Test individual metric scoring functions."""

    def test_constraint_satisfaction_budget_ok(self):
        from core.eval.eval_cases import score_constraint_satisfaction
        response = {"candidates": []}
        result = score_constraint_satisfaction(None, None, response)
        assert result.score == 0.0  # No route/constraints = 0

    def test_route_reasonableness_too_few_stops(self):
        from core.eval.eval_cases import score_route_reasonableness
        result = score_route_reasonableness(None, {})
        assert result.score == 0.0
        assert "Too few stops" in result.details

    def test_source_grounding_no_candidates(self):
        from core.eval.eval_cases import score_source_grounding
        result = score_source_grounding({"candidates": []})
        assert result.score == 0.0  # No candidates = no sourcing

    def test_source_grounding_with_trace(self):
        from core.eval.eval_cases import score_source_grounding
        result = score_source_grounding({
            "candidates": [{"source": "amap"}],
            "tool_trace": [{"tool": "AMapClient"}],
        })
        assert result.score == 2.0  # Full score

    def test_uncertainty_disclosure_no_ranges(self):
        from core.eval.eval_cases import score_uncertainty_disclosure
        result = score_uncertainty_disclosure({"candidates": []})
        assert result.score == 0.0

    def test_uncertainty_disclosure_with_ranges(self):
        from core.eval.eval_cases import score_uncertainty_disclosure
        result = score_uncertainty_disclosure({
            "candidates": [
                {"price_range": [80, 120], "is_estimated": True},
            ]
        })
        assert result.score == 2.0

    def test_safety_compliance_not_high_risk(self):
        from core.eval.eval_cases import score_safety_compliance
        result = score_safety_compliance({}, "search")
        assert result.score == 1.0  # Not high-risk = pass

    def test_safety_compliance_high_risk_not_intercepted(self):
        from core.eval.eval_cases import score_safety_compliance
        result = score_safety_compliance({}, "booking")
        assert result.score == 0.0  # High-risk but not intercepted

    def test_safety_compliance_high_risk_intercepted(self):
        from core.eval.eval_cases import score_safety_compliance
        result = score_safety_compliance({"refused": True}, "booking")
        assert result.score == 1.0  # Intercepted = pass

    def test_safety_compliance_with_warnings(self):
        from core.eval.eval_cases import score_safety_compliance
        result = score_safety_compliance(
            {"safety_warnings": ["Please confirm manually"]},
            "payment"
        )
        assert result.score == 1.0


class TestEvalSummary:
    """Test eval summary generation."""

    def test_empty_results(self):
        summary = eval_summary([])
        assert summary == {}

    def test_summary_structure(self):
        from core.eval import EvalResult
        results = [
            EvalResult("c1", EvalMetric.CONSTRAINT_SATISFACTION, 0.8, 1.0),
            EvalResult("c2", EvalMetric.CONSTRAINT_SATISFACTION, 0.6, 1.0),
        ]
        summary = eval_summary(results)
        assert "constraint_satisfaction" in summary
        assert "average" in summary["constraint_satisfaction"]
        assert "pass_rate" in summary["constraint_satisfaction"]

    def test_summary_pass_rate_calculation(self):
        from core.eval import EvalResult
        results = [
            EvalResult("c1", EvalMetric.SAFETY_COMPLIANCE, 1.0, 1.0),
            EvalResult("c2", EvalMetric.SAFETY_COMPLIANCE, 0.5, 1.0),
            EvalResult("c3", EvalMetric.SAFETY_COMPLIANCE, 0.8, 1.0),
        ]
        summary = eval_summary(results)
        # 2 out of 3 pass (≥0.7), pass_rate = 0.667
        assert summary["safety_compliance"]["passed"] == 2
        assert summary["safety_compliance"]["total"] == 3
