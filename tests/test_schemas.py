from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models import POI, POICategory, Route, RouteContext, RouteStop, UserConstraints
from schemas import (
    AdjustRequest,
    AdjustmentIntent,
    FeedbackRequest,
    ManualProfileImportRequest,
    PlanRequest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_route(stop_count: int = 3) -> Route:
    """Return the smallest valid Route that satisfies schema validation."""
    stops: list[RouteStop] = []
    for index in range(stop_count):
        poi = POI(
            id=f"poi-{index}",
            name=f"测试地点{index}",
            category=POICategory.CAFE,
            address="上海测试",
            district="黄浦区",
            latitude=31.23 + index * 0.001,
            longitude=121.47 + index * 0.001,
            rating=4.5,
            review_count=100,
            price_per_person=50,
            avg_wait_minutes=5,
            business_hours={"open": "10:00", "close": "22:00"},
            tags=["测试"],
            ugc_summary="测试用 POI",
            visit_duration_minutes=45,
        )
        stops.append(
            RouteStop(
                order=index + 1,
                poi=poi,
                arrival_time=f"{14 + index:02d}:00",
                departure_time=f"{14 + index:02d}:50",
                duration_minutes=50,
                wait_minutes=5,
            )
        )
    return Route(
        id="test-route",
        title="测试路线",
        description="schema 测试路线",
        stops=stops,
        total_time_minutes=180,
        total_cost_per_person=150.0,
        total_wait_minutes=15,
        total_transit_minutes=12,
    )


# ---------------------------------------------------------------------------
# PlanRequest
# ---------------------------------------------------------------------------

class TestPlanRequestValidation:
    """PlanRequest.query must be at least 2 characters."""

    def test_valid_query_accepted(self):
        request = PlanRequest(query="上海外滩文艺下午")
        assert request.query == "上海外滩文艺下午"
        assert request.user_id == "demo-user"
        assert request.n_routes == 2
        assert request.profile_mode == "文艺体验型"

    def test_single_char_query_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            PlanRequest(query="x")
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("query",) for error in errors)

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            PlanRequest(query="")

    def test_two_char_query_accepted(self):
        request = PlanRequest(query="逛逛")
        assert request.query == "逛逛"

    def test_n_routes_bounds(self):
        with pytest.raises(ValidationError):
            PlanRequest(query="测试", n_routes=0)
        with pytest.raises(ValidationError):
            PlanRequest(query="测试", n_routes=5)
        request = PlanRequest(query="测试", n_routes=3)
        assert request.n_routes == 3

    def test_profile_source_literal_enforced(self):
        with pytest.raises(ValidationError):
            PlanRequest(query="测试", profile_source="unknown_source")
        request = PlanRequest(query="测试", profile_source="manual_import")
        assert request.profile_source == "manual_import"

    def test_route_context_optional(self):
        request = PlanRequest(query="测试")
        assert request.route_context is None

    def test_route_context_accepted(self):
        ctx = RouteContext(source="xiaotuan", city_hint="深圳")
        request = PlanRequest(query="测试", route_context=ctx)
        assert request.route_context.city_hint == "深圳"


# ---------------------------------------------------------------------------
# FeedbackRequest
# ---------------------------------------------------------------------------

class TestFeedbackRequestValidation:
    """FeedbackRequest.feedback must be in [-1, 0, 1]."""

    def test_valid_positive_feedback(self):
        route = _make_minimal_route().model_dump()
        request = FeedbackRequest(route=route, feedback=1)
        assert request.feedback == 1

    def test_valid_zero_feedback(self):
        route = _make_minimal_route().model_dump()
        request = FeedbackRequest(route=route, feedback=0)
        assert request.feedback == 0

    def test_valid_negative_feedback(self):
        route = _make_minimal_route().model_dump()
        request = FeedbackRequest(route=route, feedback=-1)
        assert request.feedback == -1

    def test_feedback_above_range_rejected(self):
        route = _make_minimal_route().model_dump()
        with pytest.raises(ValidationError) as exc_info:
            FeedbackRequest(route=route, feedback=2)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("feedback",) for error in errors)

    def test_feedback_below_range_rejected(self):
        route = _make_minimal_route().model_dump()
        with pytest.raises(ValidationError):
            FeedbackRequest(route=route, feedback=-2)

    def test_feedback_large_positive_rejected(self):
        route = _make_minimal_route().model_dump()
        with pytest.raises(ValidationError):
            FeedbackRequest(route=route, feedback=100)

    def test_route_required(self):
        with pytest.raises(ValidationError):
            FeedbackRequest(feedback=1)


# ---------------------------------------------------------------------------
# AdjustRequest
# ---------------------------------------------------------------------------

class TestAdjustRequestValidation:
    """AdjustRequest.instruction must be at least 1 character; query at least 2."""

    def test_valid_adjust_request(self):
        route = _make_minimal_route()
        request = AdjustRequest(
            query="上海外滩下午路线",
            instruction="少走路",
            route=route,
        )
        assert request.instruction == "少走路"
        assert request.query == "上海外滩下午路线"

    def test_empty_instruction_rejected(self):
        route = _make_minimal_route()
        with pytest.raises(ValidationError) as exc_info:
            AdjustRequest(query="测试路线", instruction="", route=route)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("instruction",) for error in errors)

    def test_short_query_rejected(self):
        route = _make_minimal_route()
        with pytest.raises(ValidationError):
            AdjustRequest(query="x", instruction="少走路", route=route)

    def test_defaults(self):
        route = _make_minimal_route()
        request = AdjustRequest(query="测试查询", instruction="便宜点", route=route)
        assert request.user_id == "demo-user"
        assert request.profile_mode == "文艺体验型"
        assert request.profile_source == "preset"
        assert request.route_context is None


# ---------------------------------------------------------------------------
# ManualProfileImportRequest
# ---------------------------------------------------------------------------

class TestManualProfileImportRequest:
    """ManualProfileImportRequest allows extra fields but validates known ones."""

    def test_valid_minimal_request(self):
        request = ManualProfileImportRequest(display_name="测试画像")
        assert request.display_name == "测试画像"
        assert request.recent_searches == []
        assert request.favorite_pois == []
        assert request.browsed_pois == []

    def test_extra_fields_allowed(self):
        # extra="allow" means unknown fields are stored, not rejected
        request = ManualProfileImportRequest(
            display_name="测试画像",
            unknown_field="hello",
            another_extra=42,
        )
        assert request.display_name == "测试画像"

    def test_display_name_min_length(self):
        with pytest.raises(ValidationError):
            ManualProfileImportRequest(display_name="x")

    def test_display_name_empty_rejected(self):
        with pytest.raises(ValidationError):
            ManualProfileImportRequest(display_name="")

    def test_budget_preference_non_negative(self):
        with pytest.raises(ValidationError):
            ManualProfileImportRequest(display_name="测试", budget_preference=-10)

    def test_max_wait_preference_bounds(self):
        with pytest.raises(ValidationError):
            ManualProfileImportRequest(display_name="测试", max_wait_preference=-1)
        with pytest.raises(ValidationError):
            ManualProfileImportRequest(display_name="测试", max_wait_preference=200)
        request = ManualProfileImportRequest(display_name="测试", max_wait_preference=60)
        assert request.max_wait_preference == 60

    def test_walk_preference_default(self):
        request = ManualProfileImportRequest(display_name="测试画像")
        assert request.walk_preference == "适中"

    def test_coupon_sensitive_default_false(self):
        request = ManualProfileImportRequest(display_name="测试画像")
        assert request.coupon_sensitive is False

    def test_full_request(self):
        request = ManualProfileImportRequest(
            profile_id="test-id",
            display_name="完整画像",
            recent_searches=["咖啡", "展览"],
            favorite_pois=["某咖啡馆"],
            browsed_pois=["拍照出片"],
            favorite_categories=["咖啡/茶饮", "景点"],
            favorite_districts=["黄浦区"],
            frequent_districts=["黄浦区", "徐汇区"],
            budget_preference=200,
            max_wait_preference=15,
            walk_preference="少走路",
            coupon_sensitive=True,
        )
        assert request.profile_id == "test-id"
        assert request.coupon_sensitive is True
        assert len(request.recent_searches) == 2


# ---------------------------------------------------------------------------
# AdjustmentIntent (dataclass)
# ---------------------------------------------------------------------------

class TestAdjustmentIntent:
    """AdjustmentIntent is a dataclass with sensible defaults."""

    def test_defaults(self):
        intent = AdjustmentIntent(kind="wait")
        assert intent.kind == "wait"
        assert intent.categories is None
        assert intent.target_index is None
        assert intent.target_text is None
        assert intent.max_count is None
        assert intent.source == "rules"
        assert intent.reason == "规则兜底识别调整目标"

    def test_with_categories(self):
        intent = AdjustmentIntent(
            kind="avoid_category",
            categories={POICategory.CAFE},
        )
        assert intent.categories == {POICategory.CAFE}

    def test_with_all_fields(self):
        intent = AdjustmentIntent(
            kind="reduce_category",
            categories={POICategory.RESTAURANT},
            target_index=2,
            target_text="餐厅",
            max_count=1,
            source="llm",
            reason="LLM 识别到用户想减少餐厅",
        )
        assert intent.kind == "reduce_category"
        assert intent.target_index == 2
        assert intent.max_count == 1
        assert intent.source == "llm"

    def test_kind_is_required(self):
        with pytest.raises(TypeError):
            AdjustmentIntent()  # type: ignore[call-arg]
