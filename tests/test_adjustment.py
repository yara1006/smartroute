from __future__ import annotations

from typing import Literal

import pytest

from core.models import (
    POI,
    POICategory,
    Route,
    RouteStop,
)
from schemas import ChangedStop, MetricDeltas, RouteMetrics
from services.route_service import (
    adjustment_status_for,
    build_changed_stops,
    find_adjustment_candidate,
    parse_adjustment_intent,
    suggested_relaxations_for,
)


# ---------------------------------------------------------------------------
# Shared helpers and fixtures
# ---------------------------------------------------------------------------

def _make_poi(
    index: int,
    name: str = "",
    category: POICategory = POICategory.CAFE,
    price: float = 50.0,
    wait: int = 5,
    rating: float = 4.5,
    id_prefix: str = "adj-poi",
) -> POI:
    return POI(
        id=f"{id_prefix}-{index}",
        name=name or f"测试地点{index}",
        category=category,
        address="上海市黄浦区",
        district="黄浦区",
        latitude=31.23 + index * 0.001,
        longitude=121.47 + index * 0.001,
        rating=rating,
        review_count=200,
        price_per_person=price,
        avg_wait_minutes=wait,
        business_hours={"open": "10:00", "close": "22:00"},
        tags=[category.value],
        ugc_summary=f"调整测试 POI {index}",
        visit_duration_minutes=45,
    )


def _make_route(pois: list[POI]) -> Route:
    stops = [
        RouteStop(
            order=index + 1,
            poi=poi,
            arrival_time=f"{14 + index:02d}:00",
            departure_time=f"{14 + index:02d}:50",
            duration_minutes=50,
            wait_minutes=poi.avg_wait_minutes,
        )
        for index, poi in enumerate(pois)
    ]
    return Route(
        id="adjustment-test-route",
        title="调整测试路线",
        description="用于测试调整链",
        stops=stops,
        total_time_minutes=len(pois) * 60,
        total_cost_per_person=sum(p.price_per_person for p in pois),
        total_wait_minutes=sum(p.avg_wait_minutes for p in pois),
        total_transit_minutes=len(pois) * 5,
    )


@pytest.fixture()
def cafe_heavy_route() -> Route:
    """A route with 3 cafes and 1 attraction — ripe for 'reduce_category'."""
    return _make_route([
        _make_poi(1, "红门咖啡", POICategory.CAFE, wait=12),
        _make_poi(2, "永庆坊", POICategory.ATTRACTION, wait=5),
        _make_poi(3, "CAFE FLOWERYARDS", POICategory.CAFE, wait=8),
        _make_poi(4, "西关84咖啡厅", POICategory.CAFE, wait=10),
    ])


@pytest.fixture()
def balanced_route() -> Route:
    """A well-balanced 4-stop route."""
    return _make_route([
        _make_poi(1, "咖啡休息点", POICategory.CAFE, price=45, wait=5),
        _make_poi(2, "文化展览馆", POICategory.ATTRACTION, price=20, wait=3),
        _make_poi(3, "粤菜小馆", POICategory.RESTAURANT, price=88, wait=10),
        _make_poi(4, "步行街漫步", POICategory.SHOPPING, price=0, wait=0),
    ])


@pytest.fixture()
def candidate_pool() -> list[tuple[POI, float]]:
    """A pool of candidates for replacement tests."""
    return [
        (_make_poi(10, "粤剧艺术博物馆", POICategory.ATTRACTION, price=20, wait=4, rating=4.8), 8.0),
        (_make_poi(11, "荔湾湖公园散步点", POICategory.SHOPPING, price=10, wait=2, rating=4.7), 7.5),
        (_make_poi(12, "陶陶居粤菜馆", POICategory.RESTAURANT, price=98, wait=10, rating=4.6), 6.0),
        (_make_poi(13, "珠影影城", POICategory.ENTERTAINMENT, price=55, wait=5, rating=4.5), 5.0),
        (_make_poi(14, "精品咖啡馆", POICategory.CAFE, price=42, wait=3, rating=4.9), 9.0),
        (_make_poi(15, "便宜小吃店", POICategory.RESTAURANT, price=35, wait=2, rating=4.3), 4.0),
    ]


# ---------------------------------------------------------------------------
# parse_adjustment_intent
# ---------------------------------------------------------------------------

class TestParseAdjustmentIntent:
    """parse_adjustment_intent parses various instructions into AdjustmentIntent."""

    def test_avoid_specific_stop(self, balanced_route):
        intent = parse_adjustment_intent("我不想去咖啡休息点", balanced_route)
        assert intent.kind == "avoid_stop"
        assert intent.target_text == "咖啡休息点"
        assert intent.source == "rules"

    def test_avoid_category_negative(self, balanced_route):
        intent = parse_adjustment_intent("不要喝咖啡", balanced_route)
        assert intent.kind == "avoid_category"
        assert intent.categories is not None
        assert POICategory.CAFE in intent.categories

    def test_reduce_category(self, cafe_heavy_route):
        intent = parse_adjustment_intent("不要这么多咖啡", cafe_heavy_route)
        assert intent.kind == "reduce_category"
        assert intent.categories is not None
        assert POICategory.CAFE in intent.categories
        assert intent.max_count == 1

    def test_add_kind_fallback(self, balanced_route):
        intent = parse_adjustment_intent("加一家粤菜馆", balanced_route)
        assert intent.kind == "add"
        assert intent.categories is not None
        assert POICategory.RESTAURANT in intent.categories

    def test_wait_fallback(self, balanced_route):
        intent = parse_adjustment_intent("不排队", balanced_route)
        assert intent.kind == "wait"
        assert intent.categories is None

    def test_walk_kind(self, balanced_route):
        intent = parse_adjustment_intent("少走一点路", balanced_route)
        assert intent.kind == "walk"
        assert intent.categories is None

    def test_cheaper_kind(self, balanced_route):
        intent = parse_adjustment_intent("便宜点", balanced_route)
        assert intent.kind == "cheaper"

    def test_llm_override(self, balanced_route):
        llm_result = ("focus", {POICategory.ATTRACTION}, "llm", "LLM 判断需要更多体验类型")
        intent = parse_adjustment_intent("随便调一下", balanced_route, llm_adjustment=llm_result)
        assert intent.kind == "focus"
        assert intent.source == "llm"

    def test_mentioned_stop_with_negative(self, balanced_route):
        # "文化展览馆" is the second stop
        intent = parse_adjustment_intent("不想去文化展览馆", balanced_route)
        assert intent.kind == "avoid_stop"
        assert intent.target_text == "文化展览馆"
        assert intent.target_index == 1

    def test_default_when_no_match(self, balanced_route):
        # An instruction that doesn't match negative/reduce/specific stop
        # falls through to detect_adjustment_kind which defaults to "wait"
        intent = parse_adjustment_intent("调整一下体验", balanced_route)
        assert intent.kind == "wait"


# ---------------------------------------------------------------------------
# find_adjustment_candidate
# ---------------------------------------------------------------------------

class TestFindAdjustmentCandidate:
    """find_adjustment_candidate picks the right replacement POI."""

    def test_cheaper_finds_lower_price(self, cafe_heavy_route, candidate_pool):
        # Target is a cafe with price=50, cheaper candidate is "便宜小吃店" at 35
        # but category filter is {CAFE}, so only "精品咖啡馆" qualifies
        candidate = find_adjustment_candidate(
            cafe_heavy_route,
            candidate_pool,
            kind="cheaper",
            target_index=0,  # first cafe, price=50, wait=12
            categories={POICategory.CAFE},
        )
        # "精品咖啡馆" at price=42 is cheaper than the target at 50
        assert candidate is not None
        assert candidate.price_per_person < 50

    def test_wait_finds_lower_wait(self, cafe_heavy_route, candidate_pool):
        # Target is first cafe with wait=12
        candidate = find_adjustment_candidate(
            cafe_heavy_route,
            candidate_pool,
            kind="wait",
            target_index=0,
            categories={POICategory.CAFE},
        )
        # "精品咖啡馆" at wait=3 < 12
        assert candidate is not None
        assert candidate.avg_wait_minutes < 12

    def test_avoid_category_excludes_cafes(self, cafe_heavy_route, candidate_pool):
        candidate = find_adjustment_candidate(
            cafe_heavy_route,
            candidate_pool,
            kind="avoid_category",
            target_index=0,
            categories={POICategory.CAFE},
        )
        assert candidate is not None
        assert candidate.category != POICategory.CAFE

    def test_reduce_category_prefers_non_target(self, cafe_heavy_route, candidate_pool):
        candidate = find_adjustment_candidate(
            cafe_heavy_route,
            candidate_pool,
            kind="reduce_category",
            target_index=0,
            categories={POICategory.CAFE},
        )
        assert candidate is not None
        # When avoiding CAFE, replacement_role_rank prefers RESTAURANT (rank 0)
        # over ATTRACTION/SHOPPING/ENTERTAINMENT (rank 1), so a RESTAURANT wins
        assert candidate.category in {
            POICategory.RESTAURANT,
            POICategory.ATTRACTION,
            POICategory.SHOPPING,
            POICategory.ENTERTAINMENT,
        }
        assert candidate.category != POICategory.CAFE

    def test_add_finds_matching_category(self, balanced_route, candidate_pool):
        candidate = find_adjustment_candidate(
            balanced_route,
            candidate_pool,
            kind="add",
            target_index=0,
            categories={POICategory.ENTERTAINMENT},
        )
        assert candidate is not None
        assert candidate.category == POICategory.ENTERTAINMENT

    def test_no_matching_candidate_returns_none(self, balanced_route):
        empty_pool: list[tuple[POI, float]] = []
        candidate = find_adjustment_candidate(
            balanced_route,
            empty_pool,
            kind="cheaper",
            target_index=0,
            categories={POICategory.CAFE},
        )
        assert candidate is None

    def test_avoid_stop_replaces_with_non_target(self, cafe_heavy_route, candidate_pool):
        # Avoid the first cafe (index 0)
        candidate = find_adjustment_candidate(
            cafe_heavy_route,
            candidate_pool,
            kind="avoid_stop",
            target_index=0,
            categories={POICategory.CAFE},
        )
        assert candidate is not None
        assert candidate.id != cafe_heavy_route.stops[0].poi.id

    def test_candidate_not_already_in_route(self, cafe_heavy_route, candidate_pool):
        # All candidates in pool have different IDs from route POIs
        route_ids = {stop.poi.id for stop in cafe_heavy_route.stops}
        candidate = find_adjustment_candidate(
            cafe_heavy_route,
            candidate_pool,
            kind="avoid_category",
            target_index=0,
            categories={POICategory.CAFE},
        )
        assert candidate is not None
        assert candidate.id not in route_ids


# ---------------------------------------------------------------------------
# adjustment_status_for
# ---------------------------------------------------------------------------

class TestAdjustmentStatusFor:
    """adjustment_status_for returns the correct status string."""

    def test_not_applied_when_route_unchanged(self, balanced_route):
        deltas = MetricDeltas(
            stop_count=0,
            total_time_minutes=0,
            total_cost_per_person=0,
            total_wait_minutes=0,
            total_transit_minutes=0,
        )
        status = adjustment_status_for(
            kind="cheaper",
            before=balanced_route,
            after=balanced_route,  # same route
            changed_stops=[],
            deltas=deltas,
            candidate=None,
        )
        assert status == "not_applied"

    def test_applied_when_route_changed_with_improvement(self, balanced_route):
        # Use different id_prefix so route signature differs
        modified_pois = [
            _make_poi(1, "便宜咖啡馆", POICategory.CAFE, price=30, wait=3, id_prefix="after-poi"),
            _make_poi(2, "文化展览馆", POICategory.ATTRACTION, price=20, wait=3, id_prefix="after-poi"),
            _make_poi(3, "粤菜小馆", POICategory.RESTAURANT, price=88, wait=10, id_prefix="after-poi"),
            _make_poi(4, "步行街漫步", POICategory.SHOPPING, price=0, wait=0, id_prefix="after-poi"),
        ]
        after_route = _make_route(modified_pois)
        changed = build_changed_stops(balanced_route, after_route, [1])
        deltas = MetricDeltas(
            stop_count=0,
            total_time_minutes=0,
            total_cost_per_person=-15.0,
            total_wait_minutes=-2,
            total_transit_minutes=0,
        )
        status = adjustment_status_for(
            kind="cheaper",
            before=balanced_route,
            after=after_route,
            changed_stops=changed,
            deltas=deltas,
            candidate=modified_pois[0],
        )
        assert status == "applied"

    def test_partial_when_objective_not_improved(self, balanced_route):
        # Use different id_prefix so route signature differs, but worse cost
        modified_pois = [
            _make_poi(1, "更贵的咖啡", POICategory.CAFE, price=100, wait=20, id_prefix="after-poi"),
            _make_poi(2, "文化展览馆", POICategory.ATTRACTION, price=20, wait=3, id_prefix="after-poi"),
            _make_poi(3, "粤菜小馆", POICategory.RESTAURANT, price=88, wait=10, id_prefix="after-poi"),
            _make_poi(4, "步行街漫步", POICategory.SHOPPING, price=0, wait=0, id_prefix="after-poi"),
        ]
        after_route = _make_route(modified_pois)
        changed = build_changed_stops(balanced_route, after_route, [1])
        deltas = MetricDeltas(
            stop_count=0,
            total_time_minutes=0,
            total_cost_per_person=55.0,  # worse!
            total_wait_minutes=15,  # worse!
            total_transit_minutes=0,
        )
        status = adjustment_status_for(
            kind="cheaper",
            before=balanced_route,
            after=after_route,
            changed_stops=changed,
            deltas=deltas,
            candidate=modified_pois[0],
        )
        assert status == "partial"

    def test_partial_when_add_without_candidate(self, balanced_route):
        # Create after route with different POI IDs so route_changed is True,
        # but no actual candidate was found (add kind with candidate=None → partial)
        after_pois = [
            _make_poi(index + 1, stop.poi.name, stop.poi.category,
                       price=stop.poi.price_per_person, wait=stop.poi.avg_wait_minutes,
                       id_prefix="after-poi")
            for index, stop in enumerate(balanced_route.stops)
        ]
        after_route = _make_route(after_pois)
        changed = build_changed_stops(balanced_route, after_route, [1])
        deltas = MetricDeltas(
            stop_count=0,
            total_time_minutes=0,
            total_cost_per_person=0,
            total_wait_minutes=0,
            total_transit_minutes=0,
        )
        status = adjustment_status_for(
            kind="add",
            before=balanced_route,
            after=after_route,
            changed_stops=changed,
            deltas=deltas,
            candidate=None,  # no candidate found
        )
        assert status == "partial"

    def test_applied_for_focus_kind(self, cafe_heavy_route):
        # Use different id_prefix so route signatures differ
        modified_pois = [
            _make_poi(1, "粤剧博物馆", POICategory.ATTRACTION, price=20, wait=5, id_prefix="after-poi"),
            _make_poi(2, "永庆坊", POICategory.ATTRACTION, price=0, wait=5, id_prefix="after-poi"),
            _make_poi(3, "咖啡休息点", POICategory.CAFE, price=42, wait=3, id_prefix="after-poi"),
            _make_poi(4, "步行街", POICategory.SHOPPING, price=0, wait=0, id_prefix="after-poi"),
        ]
        after_route = _make_route(modified_pois)
        changed = build_changed_stops(cafe_heavy_route, after_route, [1, 4])
        deltas = MetricDeltas(
            stop_count=0,
            total_time_minutes=0,
            total_cost_per_person=0,
            total_wait_minutes=0,
            total_transit_minutes=0,
        )
        status = adjustment_status_for(
            kind="focus",
            before=cafe_heavy_route,
            after=after_route,
            changed_stops=changed,
            deltas=deltas,
            candidate=modified_pois[0],
        )
        assert status == "applied"


# ---------------------------------------------------------------------------
# suggested_relaxations_for
# ---------------------------------------------------------------------------

class TestSuggestedRelaxationsFor:
    """suggested_relaxations_for returns context-appropriate suggestions."""

    def test_applied_returns_empty(self):
        result = suggested_relaxations_for("cheaper", "applied", [])
        assert result == []

    def test_cheaper_suggestion(self):
        result = suggested_relaxations_for("cheaper", "partial", [])
        assert any("预算" in s for s in result)

    def test_wait_suggestion(self):
        result = suggested_relaxations_for("wait", "partial", [])
        assert any("等位" in s for s in result)

    def test_walk_suggestion(self):
        result = suggested_relaxations_for("walk", "not_applied", [])
        assert any("打车" in s for s in result)

    def test_add_suggestion(self):
        result = suggested_relaxations_for("add", "partial", [])
        assert any("延长" in s for s in result)

    def test_focus_suggestion(self):
        result = suggested_relaxations_for("focus", "partial", [])
        assert any("放宽" in s for s in result)

    def test_budget_conflict_adds_suggestion(self):
        result = suggested_relaxations_for("wait", "partial", ["预算约束较紧"])
        assert any("预算" in s for s in result)

    def test_queue_conflict_adds_suggestion(self):
        result = suggested_relaxations_for("cheaper", "partial", ["排队时间较长"])
        assert any("排队" in s or "等待" in s for s in result)

    def test_walk_conflict_adds_suggestion(self):
        result = suggested_relaxations_for("cheaper", "partial", ["步行距离偏长"])
        assert any("打车" in s or "交通" in s for s in result)

    def test_max_4_suggestions(self):
        conflicts = ["预算紧", "排队久", "走路多", "额外冲突"]
        result = suggested_relaxations_for("cheaper", "partial", conflicts)
        assert len(result) <= 4

    def test_no_duplicate_suggestions(self):
        result = suggested_relaxations_for("wait", "partial", ["排队等待久"])
        # Should not have duplicates
        assert len(result) == len(set(result))


# ---------------------------------------------------------------------------
# build_changed_stops
# ---------------------------------------------------------------------------

class TestBuildChangedStops:
    """build_changed_stops correctly identifies changes between routes."""

    def test_no_changes(self, balanced_route):
        changes = build_changed_stops(balanced_route, balanced_route, [])
        assert changes == []

    def test_replaced_stop(self, balanced_route):
        new_poi = _make_poi(99, "替换景点", POICategory.ATTRACTION, price=30, wait=5)
        modified_stops = list(balanced_route.stops)
        modified_stops[0] = RouteStop(
            order=1,
            poi=new_poi,
            arrival_time="14:00",
            departure_time="14:50",
            duration_minutes=50,
            wait_minutes=5,
        )
        after_route = Route(
            id="after-route",
            title="替换后路线",
            description="测试",
            stops=modified_stops,
            total_time_minutes=balanced_route.total_time_minutes,
            total_cost_per_person=balanced_route.total_cost_per_person,
            total_wait_minutes=balanced_route.total_wait_minutes,
            total_transit_minutes=balanced_route.total_transit_minutes,
        )
        changes = build_changed_stops(balanced_route, after_route, [1])
        assert len(changes) == 1
        assert changes[0].order == 1
        assert changes[0].action == "replaced"
        assert changes[0].before_poi == "咖啡休息点"
        assert changes[0].after_poi == "替换景点"

    def test_added_stop(self, balanced_route):
        new_poi = _make_poi(99, "新增景点", POICategory.ATTRACTION)
        extra_stop = RouteStop(
            order=len(balanced_route.stops) + 1,
            poi=new_poi,
            arrival_time="18:00",
            departure_time="18:50",
            duration_minutes=50,
            wait_minutes=5,
        )
        after_stops = list(balanced_route.stops) + [extra_stop]
        after_route = Route(
            id="after-route",
            title="新增后路线",
            description="测试",
            stops=after_stops,
            total_time_minutes=balanced_route.total_time_minutes + 60,
            total_cost_per_person=balanced_route.total_cost_per_person,
            total_wait_minutes=balanced_route.total_wait_minutes + 5,
            total_transit_minutes=balanced_route.total_transit_minutes,
        )
        changes = build_changed_stops(balanced_route, after_route, [5])
        added = [c for c in changes if c.action == "added"]
        assert len(added) == 1
        assert added[0].after_poi == "新增景点"

    def test_removed_stop(self, balanced_route):
        after_stops = balanced_route.stops[:3]  # remove the 4th stop
        after_route = Route(
            id="after-route",
            title="移除后路线",
            description="测试",
            stops=after_stops,
            total_time_minutes=balanced_route.total_time_minutes - 60,
            total_cost_per_person=balanced_route.total_cost_per_person,
            total_wait_minutes=balanced_route.total_wait_minutes,
            total_transit_minutes=balanced_route.total_transit_minutes,
        )
        changes = build_changed_stops(balanced_route, after_route, [])
        removed = [c for c in changes if c.action == "removed"]
        assert len(removed) == 1
        assert removed[0].before_poi == "步行街漫步"

    def test_reordered_stop(self, balanced_route):
        # Swap stops 0 and 1
        swapped_stops = [balanced_route.stops[1], balanced_route.stops[0]] + balanced_route.stops[2:]
        after_route = Route(
            id="after-route",
            title="重排后路线",
            description="测试",
            stops=swapped_stops,
            total_time_minutes=balanced_route.total_time_minutes,
            total_cost_per_person=balanced_route.total_cost_per_person,
            total_wait_minutes=balanced_route.total_wait_minutes,
            total_transit_minutes=balanced_route.total_transit_minutes,
        )
        changes = build_changed_stops(balanced_route, after_route, [])
        reordered = [c for c in changes if c.action == "reordered"]
        assert len(reordered) == 2
        orders = {c.order for c in reordered}
        assert 1 in orders
        assert 2 in orders

    def test_unchanged_stops_not_in_changes(self, balanced_route):
        # Only change stop 0, stops 1-3 should not appear
        new_poi = _make_poi(99, "新站点", POICategory.CAFE)
        modified_stops = list(balanced_route.stops)
        modified_stops[0] = RouteStop(
            order=1,
            poi=new_poi,
            arrival_time="14:00",
            departure_time="14:50",
            duration_minutes=50,
            wait_minutes=5,
        )
        after_route = Route(
            id="after-route",
            title="测试",
            description="测试",
            stops=modified_stops,
            total_time_minutes=balanced_route.total_time_minutes,
            total_cost_per_person=balanced_route.total_cost_per_person,
            total_wait_minutes=balanced_route.total_wait_minutes,
            total_transit_minutes=balanced_route.total_transit_minutes,
        )
        changes = build_changed_stops(balanced_route, after_route, [1])
        changed_orders = {c.order for c in changes}
        assert 1 in changed_orders
        # Stops 2, 3, 4 should NOT be in changes (unchanged)
        assert 2 not in changed_orders
        assert 3 not in changed_orders
        assert 4 not in changed_orders
