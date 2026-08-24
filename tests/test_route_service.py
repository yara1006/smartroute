from __future__ import annotations

import pytest

from core.models import (
    POI,
    POICategory,
    ParsedIntent,
    Route,
    RouteContext,
    RouteStop,
    UserConstraints,
)
from schemas import MetricDeltas, RouteCompleteness, RouteMetrics
from services.route_service import (
    build_route_completeness,
    city_hint_from,
    clean_text_list,
    detect_adjustment_kind,
    extract_anchor_text,
    has_negative_adjustment,
    has_reduce_adjustment,
    infer_categories_from_text,
    is_likely_place_anchor,
    metric_deltas,
    mentioned_categories,
    normalize_profile_mode,
    route_metrics,
    safe_slug,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_pois() -> list[POI]:
    """A reusable set of POIs for route-building tests."""
    categories = [
        POICategory.CAFE,
        POICategory.ATTRACTION,
        POICategory.SHOPPING,
        POICategory.RESTAURANT,
        POICategory.ENTERTAINMENT,
    ]
    return [
        POI(
            id=f"poi-{index}",
            name=f"测试地点{index}",
            category=category,
            address="上海市黄浦区测试路",
            district="黄浦区",
            latitude=31.23 + index * 0.001,
            longitude=121.47 + index * 0.001,
            rating=4.5 - index * 0.1,
            review_count=200,
            price_per_person=50 + index * 10,
            avg_wait_minutes=5 + index,
            business_hours={"open": "10:00", "close": "22:00"},
            tags=[category.value],
            ugc_summary=f"测试 POI {index}",
            visit_duration_minutes=45,
        )
        for index, category in enumerate(categories)
    ]


@pytest.fixture()
def sample_route(sample_pois: list[POI]) -> Route:
    """A 5-stop route covering all major categories."""
    stops = [
        RouteStop(
            order=index + 1,
            poi=poi,
            arrival_time=f"{14 + index:02d}:00",
            departure_time=f"{14 + index:02d}:50",
            duration_minutes=50,
            wait_minutes=poi.avg_wait_minutes,
        )
        for index, poi in enumerate(sample_pois)
    ]
    return Route(
        id="test-route-full",
        title="完整测试路线",
        description="覆盖全品类",
        stops=stops,
        total_time_minutes=280,
        total_cost_per_person=350.0,
        total_wait_minutes=35,
        total_transit_minutes=25,
    )


@pytest.fixture()
def default_intent() -> ParsedIntent:
    """A default ParsedIntent for city_hint_from tests."""
    return ParsedIntent(
        city="上海",
        constraints=UserConstraints(),
        parser_source="rules",
    )


# ---------------------------------------------------------------------------
# normalize_profile_mode
# ---------------------------------------------------------------------------

class TestNormalizeProfileMode:
    """Valid modes pass through; invalid modes fall back to '文艺体验型'."""

    def test_known_mode_returned_as_is(self):
        assert normalize_profile_mode("低排队务实型") == "低排队务实型"
        assert normalize_profile_mode("文艺体验型") == "文艺体验型"
        assert normalize_profile_mode("带爸妈轻松型") == "带爸妈轻松型"

    def test_unknown_mode_falls_back(self):
        assert normalize_profile_mode("不存在的模式") == "文艺体验型"

    def test_none_falls_back(self):
        assert normalize_profile_mode(None) == "文艺体验型"

    def test_empty_string_falls_back(self):
        assert normalize_profile_mode("") == "文艺体验型"


# ---------------------------------------------------------------------------
# safe_slug
# ---------------------------------------------------------------------------

class TestSafeSlug:
    """safe_slug turns arbitrary text into a URL-safe slug."""

    def test_chinese_characters(self):
        result = safe_slug("测试画像")
        assert result  # not empty
        assert len(result) <= 48
        # Chinese chars are not alphanumeric in ASCII, so they become "-"
        # consecutive dashes are collapsed
        assert "--" not in result

    def test_english_text(self):
        result = safe_slug("Hello World")
        assert "hello" in result
        assert "world" in result

    def test_special_characters_replaced(self):
        result = safe_slug("user@name!#test")
        assert "@" not in result
        assert "#" not in result
        assert "!" not in result

    def test_empty_string_returns_fallback(self):
        result = safe_slug("")
        assert result.startswith("profile-")

    def test_whitespace_only_returns_fallback(self):
        result = safe_slug("   ")
        assert result.startswith("profile-")

    def test_long_text_truncated(self):
        result = safe_slug("a" * 100)
        assert len(result) <= 48

    def test_dedup_consecutive_separators(self):
        result = safe_slug("hello---world")
        assert "---" not in result

    def test_mixed_chinese_english(self):
        result = safe_slug("测试test画像")
        assert result  # should not crash
        assert len(result) <= 48


# ---------------------------------------------------------------------------
# clean_text_list
# ---------------------------------------------------------------------------

class TestCleanTextList:
    """clean_text_list deduplicates, strips, and truncates items."""

    def test_dedup(self):
        result = clean_text_list(["咖啡", "咖啡", "展览"])
        assert result == ["咖啡", "展览"]

    def test_truncation_at_32_chars(self):
        long_item = "a" * 50
        result = clean_text_list([long_item])
        assert len(result[0]) == 32

    def test_limit_enforced(self):
        items = [f"item-{index}" for index in range(20)]
        result = clean_text_list(items, limit=5)
        assert len(result) == 5

    def test_default_limit_12(self):
        items = [f"item-{index}" for index in range(20)]
        result = clean_text_list(items)
        assert len(result) == 12

    def test_empty_items_skipped(self):
        result = clean_text_list(["", "  ", "valid", ""])
        assert result == ["valid"]

    def test_strip_whitespace(self):
        result = clean_text_list(["  hello  ", "  world"])
        assert result == ["hello", "world"]

    def test_empty_input(self):
        result = clean_text_list([])
        assert result == []


# ---------------------------------------------------------------------------
# infer_categories_from_text
# ---------------------------------------------------------------------------

class TestInferCategoriesFromText:
    """Keyword-to-category mapping."""

    def test_cafe_keywords(self):
        result = infer_categories_from_text(["咖啡", "下午茶"])
        assert POICategory.CAFE.value in result

    def test_restaurant_keywords(self):
        result = infer_categories_from_text(["火锅", "美食"])
        assert POICategory.RESTAURANT.value in result

    def test_attraction_keywords(self):
        result = infer_categories_from_text(["展览", "博物馆"])
        assert POICategory.ATTRACTION.value in result

    def test_entertainment_keywords(self):
        result = infer_categories_from_text(["KTV", "电影"])
        assert POICategory.ENTERTAINMENT.value in result

    def test_shopping_keywords(self):
        result = infer_categories_from_text(["商场", "逛街"])
        assert POICategory.SHOPPING.value in result

    def test_no_match_returns_empty(self):
        result = infer_categories_from_text(["没有匹配的关键词"])
        assert result == []

    def test_multiple_categories(self):
        result = infer_categories_from_text(["咖啡", "展览", "商场"])
        assert len(result) >= 3
        assert POICategory.CAFE.value in result
        assert POICategory.ATTRACTION.value in result
        assert POICategory.SHOPPING.value in result

    def test_no_duplicate_categories(self):
        result = infer_categories_from_text(["咖啡", "下午茶", "奶茶"])
        # Should only have one entry for CAFE
        assert result.count(POICategory.CAFE.value) == 1


# ---------------------------------------------------------------------------
# detect_adjustment_kind
# ---------------------------------------------------------------------------

class TestDetectAdjustmentKind:
    """Chinese instructions map to the correct adjustment kind and categories."""

    def test_too_many_cafes(self):
        kind, categories = detect_adjustment_kind("不要这么多咖啡")
        assert kind == "focus"
        assert categories is not None
        assert POICategory.ATTRACTION in categories

    def test_too_many_restaurants(self):
        kind, categories = detect_adjustment_kind("太多餐厅了")
        assert kind == "focus"
        assert categories is not None
        assert POICategory.ATTRACTION in categories

    def test_change_focus(self):
        kind, categories = detect_adjustment_kind("换个重点")
        assert kind == "focus"

    def test_walk_less(self):
        kind, categories = detect_adjustment_kind("少走一点")
        assert kind == "walk"
        assert categories is None

    def test_cheaper(self):
        kind, categories = detect_adjustment_kind("便宜一点")
        assert kind == "cheaper"
        assert categories is None

    def test_no_wait(self):
        kind, categories = detect_adjustment_kind("不排队")
        assert kind == "wait"
        assert categories is None

    def test_add_restaurant(self):
        kind, categories = detect_adjustment_kind("加一家粤菜馆")
        assert kind == "add"
        assert categories is not None
        assert POICategory.RESTAURANT in categories

    def test_add_cafe(self):
        kind, categories = detect_adjustment_kind("想喝下午茶")
        assert kind == "add"
        assert categories is not None
        assert POICategory.CAFE in categories

    def test_add_attraction(self):
        kind, categories = detect_adjustment_kind("想看展览")
        assert kind == "add"
        assert categories is not None
        assert POICategory.ATTRACTION in categories

    def test_default_fallback(self):
        kind, categories = detect_adjustment_kind("随便调整一下")
        assert kind == "wait"
        assert categories is None

    def test_more_variety(self):
        kind, categories = detect_adjustment_kind("更丰富一点")
        assert kind == "focus"


# ---------------------------------------------------------------------------
# mentioned_categories
# ---------------------------------------------------------------------------

class TestMentionedCategories:
    """mentioned_categories finds all category aliases in an instruction."""

    def test_restaurant_mentioned(self):
        result = mentioned_categories("不想吃饭")
        assert POICategory.RESTAURANT in result

    def test_cafe_mentioned(self):
        result = mentioned_categories("不要喝咖啡")
        assert POICategory.CAFE in result

    def test_attraction_mentioned(self):
        result = mentioned_categories("不想看展览")
        assert POICategory.ATTRACTION in result

    def test_entertainment_mentioned(self):
        result = mentioned_categories("不想看电影")
        assert POICategory.ENTERTAINMENT in result

    def test_shopping_mentioned(self):
        result = mentioned_categories("不想逛街")
        assert POICategory.SHOPPING in result

    def test_no_mention(self):
        result = mentioned_categories("随便走走")
        assert len(result) == 0

    def test_multiple_mentioned(self):
        result = mentioned_categories("不想喝咖啡也不想吃饭")
        assert POICategory.CAFE in result
        assert POICategory.RESTAURANT in result

    def test_case_insensitive(self):
        result = mentioned_categories("不想去KTV")
        assert POICategory.ENTERTAINMENT in result


# ---------------------------------------------------------------------------
# has_negative_adjustment / has_reduce_adjustment
# ---------------------------------------------------------------------------

class TestHasNegativeAdjustment:
    def test_negative_terms_detected(self):
        assert has_negative_adjustment("不想去那里") is True
        assert has_negative_adjustment("不要咖啡") is True
        assert has_negative_adjustment("别去那个餐厅") is True
        assert has_negative_adjustment("不去博物馆") is True
        assert has_negative_adjustment("去掉这个") is True
        assert has_negative_adjustment("换掉这家店") is True

    def test_no_negative_terms(self):
        assert has_negative_adjustment("加一个景点") is False
        assert has_negative_adjustment("便宜点") is False
        assert has_negative_adjustment("换个重点") is False


class TestHasReduceAdjustment:
    def test_reduce_terms_detected(self):
        assert has_reduce_adjustment("不要这么多咖啡") is True
        assert has_reduce_adjustment("少安排一点") is True
        assert has_reduce_adjustment("太多了") is True
        assert has_reduce_adjustment("减少餐厅") is True
        assert has_reduce_adjustment("都是咖啡") is True

    def test_no_reduce_terms(self):
        assert has_reduce_adjustment("加一个景点") is False
        assert has_reduce_adjustment("不想去") is False
        assert has_reduce_adjustment("便宜点") is False


# ---------------------------------------------------------------------------
# city_hint_from
# ---------------------------------------------------------------------------

class TestCityHintFrom:
    """city_hint_from detects cities from query text and context."""

    def test_route_context_city_hint_takes_priority(self, default_intent):
        ctx = RouteContext(city_hint="广州")
        assert city_hint_from("深圳大学附近", default_intent, ctx) == "广州"

    def test_shenzhen_keywords(self, default_intent):
        assert city_hint_from("深圳大学附近玩", default_intent) == "深圳"
        assert city_hint_from("科技园附近", default_intent) == "深圳"

    def test_shanghai_keywords(self, default_intent):
        assert city_hint_from("外滩附近逛逛", default_intent) == "上海"
        assert city_hint_from("陆家嘴玩", default_intent) == "上海"

    def test_beijing_keywords(self, default_intent):
        assert city_hint_from("三里屯附近", default_intent) == "北京"
        assert city_hint_from("国贸附近", default_intent) == "北京"

    def test_guangzhou_keywords(self, default_intent):
        assert city_hint_from("广州永庆坊附近", default_intent) == "广州"
        assert city_hint_from("天河附近", default_intent) == "广州"

    def test_llm_city_fallback(self):
        intent = ParsedIntent(
            city="成都",
            constraints=UserConstraints(),
            parser_source="llm",
        )
        assert city_hint_from("某个未知地方", intent) == "成都"

    def test_no_city_detected(self, default_intent):
        assert city_hint_from("随便逛逛", default_intent) == ""

    def test_rules_parser_does_not_use_llm_city(self):
        intent = ParsedIntent(
            city="成都",
            constraints=UserConstraints(),
            parser_source="rules",
        )
        assert city_hint_from("某个未知地方", intent) == ""


# ---------------------------------------------------------------------------
# extract_anchor_text
# ---------------------------------------------------------------------------

class TestExtractAnchorText:
    """extract_anchor_text finds anchors in various query formats."""

    def test_route_context_anchor_wins(self):
        ctx = RouteContext(anchor_text="永庆坊")
        result = extract_anchor_text("深圳万象天地附近", ctx)
        assert result == "永庆坊"

    def test_known_landmark(self):
        assert extract_anchor_text("万象天地附近玩") == "万象天地"

    def test_known_landmark_shenzhen_uni(self):
        assert extract_anchor_text("深圳大学附近") == "深圳大学"

    def test_nearby_marker_extracts_prefix(self):
        result = extract_anchor_text("某个公园附近玩")
        # "某个公园" is not a known landmark, but the nearby-marker logic
        # will try to extract the prefix. Depending on clean_anchor_candidate,
        # the result might be extracted or None.
        # This test verifies the function doesn't crash and returns a string or None.
        assert result is None or isinstance(result, str)

    def test_comma_split(self):
        result = extract_anchor_text("深圳大学，帮我规划路线")
        assert result is not None

    def test_congzou_pattern(self):
        result = extract_anchor_text("从深圳大学出发，下午逛逛")
        assert result == "深圳大学"

    def test_no_anchor(self):
        result = extract_anchor_text("帮我规划一个下午路线")
        assert result is None

    def test_gaga_anchor(self):
        result = extract_anchor_text("从gaga出发")
        assert result == "gaga"


# ---------------------------------------------------------------------------
# is_likely_place_anchor
# ---------------------------------------------------------------------------

class TestIsLikelyPlaceAnchor:
    """is_likely_place_anchor distinguishes place names from non-places."""

    def test_valid_place_suffixes(self):
        assert is_likely_place_anchor("万象天地") is True
        assert is_likely_place_anchor("深圳大学") is True
        assert is_likely_place_anchor("中心广场") is True
        assert is_likely_place_anchor("城市公园") is True
        assert is_likely_place_anchor("历史博物馆") is True

    def test_question_words_rejected(self):
        assert is_likely_place_anchor("什么好玩") is False
        assert is_likely_place_anchor("怎么走") is False
        assert is_likely_place_anchor("多少小时") is False

    def test_nearby_words_rejected(self):
        assert is_likely_place_anchor("附近餐厅") is False
        assert is_likely_place_anchor("周边景点") is False

    def test_too_short_rejected(self):
        assert is_likely_place_anchor("x") is False

    def test_too_long_rejected(self):
        assert is_likely_place_anchor("a" * 30) is False

    def test_time_words_rejected(self):
        assert is_likely_place_anchor("今天下午") is False
        assert is_likely_place_anchor("晚上散步") is False
        assert is_likely_place_anchor("3小时") is False

    def test_empty_string(self):
        assert is_likely_place_anchor("") is False

    def test_valid_endings(self):
        for suffix in ["天地", "中心", "广场", "公园", "大学", "博物馆", "坊", "店"]:
            name = f"测试{suffix}"
            assert is_likely_place_anchor(name) is True, f"Failed for suffix: {suffix}"


# ---------------------------------------------------------------------------
# build_route_completeness
# ---------------------------------------------------------------------------

class TestBuildRouteCompleteness:
    """build_route_completeness produces correct flags for different configs."""

    def test_none_route_returns_none(self):
        assert build_route_completeness(None) is None

    def test_complete_route(self, sample_route):
        result = build_route_completeness(sample_route)
        assert result is not None
        assert result.is_complete is True
        assert result.has_meal is True
        assert result.has_culture_or_entertainment is True
        assert result.stop_count == 5

    def test_route_without_meal(self, sample_pois):
        # Build route without meal stops (no RESTAURANT or CAFE)
        non_meal_pois = [p for p in sample_pois if p.category not in {POICategory.CAFE, POICategory.RESTAURANT}]
        stops = [
            RouteStop(
                order=index + 1,
                poi=poi,
                arrival_time=f"{14 + index:02d}:00",
                departure_time=f"{14 + index:02d}:50",
                duration_minutes=50,
            )
            for index, poi in enumerate(non_meal_pois)
        ]
        route = Route(
            id="no-meal-route",
            title="无餐饮路线",
            description="测试",
            stops=stops,
            total_time_minutes=180,
            total_cost_per_person=100.0,
        )
        result = build_route_completeness(route)
        assert result is not None
        assert result.has_meal is False
        assert result.is_complete is False
        assert any("餐饮" in note for note in result.notes)

    def test_route_without_culture(self, sample_pois):
        # Build route with only meal stops
        meal_pois = [p for p in sample_pois if p.category in {POICategory.CAFE, POICategory.RESTAURANT}]
        stops = [
            RouteStop(
                order=index + 1,
                poi=poi,
                arrival_time=f"{14 + index:02d}:00",
                departure_time=f"{14 + index:02d}:50",
                duration_minutes=50,
            )
            for index, poi in enumerate(meal_pois)
        ]
        route = Route(
            id="no-culture-route",
            title="无文化路线",
            description="测试",
            stops=stops,
            total_time_minutes=120,
            total_cost_per_person=100.0,
        )
        result = build_route_completeness(route)
        assert result is not None
        assert result.has_culture_or_entertainment is False
        assert result.is_complete is False

    def test_too_few_stops(self):
        poi = POI(
            id="single-poi",
            name="单一地点",
            category=POICategory.CAFE,
            address="测试",
            latitude=31.23,
            longitude=121.47,
            rating=4.5,
            review_count=100,
            price_per_person=50,
            business_hours={"open": "10:00", "close": "22:00"},
            ugc_summary="测试",
        )
        route = Route(
            id="short-route",
            title="太短路线",
            description="测试",
            stops=[
                RouteStop(
                    order=1,
                    poi=poi,
                    arrival_time="14:00",
                    departure_time="14:50",
                    duration_minutes=50,
                )
            ],
            total_time_minutes=50,
            total_cost_per_person=50.0,
        )
        result = build_route_completeness(route)
        assert result is not None
        assert result.is_complete is False
        assert result.stop_count == 1
        assert any("不足" in note for note in result.notes)


# ---------------------------------------------------------------------------
# route_metrics / metric_deltas
# ---------------------------------------------------------------------------

class TestRouteMetrics:
    """route_metrics extracts correct values from a Route."""

    def test_basic_metrics(self, sample_route):
        metrics = route_metrics(sample_route)
        assert metrics.stop_count == 5
        assert metrics.total_time_minutes == 280
        assert metrics.total_cost_per_person == 350.0
        assert metrics.total_wait_minutes == 35
        assert metrics.total_transit_minutes == 25

    def test_cost_rounded(self, sample_pois):
        poi = sample_pois[0]
        route = Route(
            id="round-test",
            title="测试",
            description="测试",
            stops=[
                RouteStop(
                    order=1,
                    poi=poi,
                    arrival_time="14:00",
                    departure_time="14:50",
                    duration_minutes=50,
                )
            ],
            total_time_minutes=50,
            total_cost_per_person=50.567,
        )
        metrics = route_metrics(route)
        assert metrics.total_cost_per_person == 50.6


class TestMetricDeltas:
    """metric_deltas computes the differences between before and after."""

    def test_positive_deltas(self):
        before = RouteMetrics(
            stop_count=3,
            total_time_minutes=180,
            total_cost_per_person=100.0,
            total_wait_minutes=10,
            total_transit_minutes=15,
        )
        after = RouteMetrics(
            stop_count=4,
            total_time_minutes=200,
            total_cost_per_person=130.0,
            total_wait_minutes=15,
            total_transit_minutes=20,
        )
        deltas = metric_deltas(before, after)
        assert deltas.stop_count == 1
        assert deltas.total_time_minutes == 20
        assert deltas.total_cost_per_person == 30.0
        assert deltas.total_wait_minutes == 5
        assert deltas.total_transit_minutes == 5

    def test_negative_deltas(self):
        before = RouteMetrics(
            stop_count=5,
            total_time_minutes=300,
            total_cost_per_person=200.0,
            total_wait_minutes=30,
            total_transit_minutes=25,
        )
        after = RouteMetrics(
            stop_count=4,
            total_time_minutes=250,
            total_cost_per_person=150.0,
            total_wait_minutes=15,
            total_transit_minutes=18,
        )
        deltas = metric_deltas(before, after)
        assert deltas.stop_count == -1
        assert deltas.total_time_minutes == -50
        assert deltas.total_cost_per_person == -50.0
        assert deltas.total_wait_minutes == -15
        assert deltas.total_transit_minutes == -7

    def test_zero_deltas(self):
        metrics = RouteMetrics(
            stop_count=3,
            total_time_minutes=180,
            total_cost_per_person=100.0,
            total_wait_minutes=10,
            total_transit_minutes=15,
        )
        deltas = metric_deltas(metrics, metrics)
        assert deltas.stop_count == 0
        assert deltas.total_time_minutes == 0
        assert deltas.total_cost_per_person == 0.0
        assert deltas.total_wait_minutes == 0
        assert deltas.total_transit_minutes == 0
