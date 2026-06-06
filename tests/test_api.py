from fastapi.testclient import TestClient

import api
from api import app, load_agents
from core.agents.intent_parser import IntentParserAgent
from core.models import GeoPoint, POI, POICategory


def make_adjust_test_poi(name, category, index, price=60, wait=8, rating=4.6):
    return {
        "id": f"adjust-poi-{index}",
        "name": name,
        "category": category.value,
        "address": "广州永庆坊附近",
        "district": "广州",
        "latitude": 23.114 + index * 0.001,
        "longitude": 113.25 + index * 0.001,
        "rating": rating,
        "review_count": 500,
        "price_per_person": price,
        "avg_wait_minutes": wait,
        "business_hours": {"open": "10:00", "close": "22:00"},
        "tags": [category.value],
        "ugc_summary": f"{name} 测试候选",
        "visit_duration_minutes": 45,
        "source": "amap",
        "distance_from_anchor_meters": 200 + index * 100,
    }


def make_adjust_test_route(pois):
    stops = []
    for index, poi in enumerate(pois, start=1):
        hour = 14 + index - 1
        stops.append(
            {
                "order": index,
                "poi": poi,
                "arrival_time": f"{hour:02d}:00",
                "departure_time": f"{hour:02d}:50",
                "duration_minutes": 50,
                "wait_minutes": poi["avg_wait_minutes"],
                "transit_to_next": "步行约6分钟",
                "transit_minutes": 6 if index < len(pois) else 0,
                "tips": "测试路线",
            }
        )
    return {
        "id": "coffee-heavy-adjust-route",
        "title": "荔湾文艺实时调整",
        "description": "测试咖啡过多的调整链路",
        "stops": stops,
        "total_time_minutes": 260,
        "total_cost_per_person": sum(poi["price_per_person"] for poi in pois),
        "total_wait_minutes": sum(poi["avg_wait_minutes"] for poi in pois),
        "total_transit_minutes": 18,
        "highlights": ["测试路线"],
        "warnings": [],
    }


def test_plan_api_returns_real_routes():
    client = TestClient(app)
    response = client.post(
        "/api/plan",
        json={
            "query": "帮我规划一个上海外滩附近的文艺下午，时间3小时，两个人，预算200，不想排队",
            "user_id": "api-test-user",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidates"]
    assert payload["routes"]
    assert len(payload["routes"][0]["route"]["stops"]) >= 3
    assert payload["routes"][0]["insight"]["confidence_score"] >= 45
    categories = {stop["poi"]["category"] for stop in payload["routes"][0]["route"]["stops"]}
    assert categories.intersection({"餐饮", "咖啡/茶饮"})
    assert categories.intersection({"景点", "娱乐"})
    hits = payload["routes"][0]["insight"]["constraint_hits"]
    assert ">=3 POI" in hits
    assert "餐饮+文化/娱乐/散步覆盖" in hits


def test_unknown_poi_prompt_returns_complete_route():
    client = TestClient(app)
    response = client.post(
        "/api/plan",
        json={
            "query": "我下午要去外滩玩3个小时，帮我规划一个路线",
            "user_id": "unknown-poi-test-user",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    route = payload["routes"][0]["route"]
    assert len(route["stops"]) >= 3
    assert route["total_time_minutes"] <= 3 * 60 + 45
    assert payload["planning_time_ms"] >= 0
    assert payload["meituan_user_context"]["profile_mode"] == "文艺体验型"
    assert payload["route_completeness"]["is_complete"] is True
    assert payload["profile_influence"]
    assert payload["follow_up"]["question"]
    assert len(payload["follow_up"]["options"]) >= 3
    assert payload["follow_up"]["options"][0]["instruction"]
    assert payload["intent"]["parser_source"] in {"rules", "llm"}
    assert payload["tool_trace"]


def test_adjust_endpoint_returns_structured_results(monkeypatch):
    monkeypatch.setattr(api, "classify_adjustment_with_deepseek", lambda *_args, **_kwargs: None)
    client = TestClient(app)
    plan_response = client.post(
        "/api/plan",
        json={
            "query": "帮我规划一个上海外滩附近的文艺下午，时间3小时，两个人，预算200，不想排队",
            "user_id": "adjust-structured-test-user",
        },
    )
    assert plan_response.status_code == 200
    route = plan_response.json()["routes"][0]["route"]

    for instruction in ["少走路", "不要排队", "便宜点", "换个重点"]:
        response = client.post(
            "/api/adjust",
            json={
                "query": "帮我规划一个上海外滩附近的文艺下午，时间3小时，两个人，预算200，不想排队",
                "instruction": instruction,
                "route": route,
                "user_id": "adjust-structured-test-user",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["adjustment_status"] in {"applied", "partial", "not_applied"}
        assert payload["metric_deltas"]
        assert payload["tool_trace"]
        assert payload["adjustment_history_item"]


def test_explicit_anchor_does_not_fallback_to_shanghai_local_rag(monkeypatch):
    class FakeAMapClient:
        enabled = True

        def resolve_anchor(self, text=None, city_hint=None, anchor_location=None):
            return api.AMapAnchor(
                text=text or "北京金鱼胡同",
                city="北京",
                location=GeoPoint(latitude=39.915536, longitude=116.415007),
                source="fake_poi_text",
            )

        def search_pois(self, anchor, categories, keywords=None, radius_meters=3000, limit_per_category=8):
            return []

        def route_segment(self, origin, destination, mode="步行+公交", city=None):
            return None

        def recent_errors(self):
            return ["place/around: mock no result"]

    monkeypatch.setattr(api, "AMapClient", FakeAMapClient)
    client = TestClient(app)
    response = client.post(
        "/api/plan",
        json={
            "query": "在北京金鱼胡同附近玩3个小时，帮我规划一个路线",
            "user_id": "beijing-anchor-no-local-rag-test-user",
            "route_context": {
                "source": "xiaotuan",
                "city_hint": "北京",
                "anchor_text": "北京金鱼胡同",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"]["city"] == "北京"
    assert "黄浦区" not in payload["intent"]["constraints"]["preferred_districts"]
    assert "徐汇区" not in payload["intent"]["constraints"]["preferred_districts"]
    assert payload["intent"]["extracted_preferences"]["anchor_text"] == "北京金鱼胡同"
    assert payload["candidates"] == []
    assert payload["routes"] == []
    assert any("未使用本地 RAG" in item for item in payload["trace"])


def test_short_xiaotuan_place_query_extracts_anchor_from_planning_phrase(monkeypatch):
    class FakeAMapClient:
        enabled = True

        def resolve_anchor(self, text=None, city_hint=None, anchor_location=None):
            assert text == "万象天地"
            assert city_hint == "深圳"
            return api.AMapAnchor(
                text=text,
                city="深圳",
                location=GeoPoint(latitude=22.5408, longitude=113.9462),
                source="fake_poi_text",
            )

        def search_pois(self, anchor, categories, keywords=None, radius_meters=3000, limit_per_category=8):
            return api.fallback_pois_around_anchor(anchor, categories, count_per_category=1)

        def route_segment(self, origin, destination, mode="步行+公交", city=None):
            return None

    monkeypatch.setattr(api, "AMapClient", FakeAMapClient)
    client = TestClient(app)
    response = client.post(
        "/api/plan",
        json={
            "query": "万象天地，帮我规划成一条可执行路线",
            "user_id": "wanxiang-short-query-test-user",
            "route_context": {"source": "xiaotuan", "city_hint": "深圳"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"]["city"] == "深圳"
    assert payload["intent"]["extracted_preferences"]["anchor_text"] == "万象天地"
    assert payload["intent"]["extracted_preferences"]["anchor_source"] == "fake_poi_text"
    assert all(stop["poi"]["district"] == "深圳" for stop in payload["routes"][0]["route"]["stops"])


def test_live_anchor_does_not_fake_route_with_multiple_restaurants(monkeypatch):
    def make_amap_poi(name, category, index):
        return POI(
            id=f"amap-food-heavy-{index}",
            name=name,
            category=category,
            address="广州永庆坊附近",
            district="广州",
            latitude=23.114 + index * 0.001,
            longitude=113.25 + index * 0.001,
            rating=4.8 - index * 0.05,
            review_count=500,
            price_per_person=80,
            avg_wait_minutes=8,
            business_hours={"open": "10:00", "close": "22:00"},
            tags=[category.value],
            ugc_summary="高德测试候选",
            visit_duration_minutes=45,
            source="amap",
            distance_from_anchor_meters=200 + index * 80,
        )

    class FakeAMapClient:
        enabled = True

        def resolve_anchor(self, text=None, city_hint=None, anchor_location=None):
            return api.AMapAnchor(
                text=text or "广州永庆坊",
                city="广州",
                location=GeoPoint(latitude=23.114, longitude=113.25),
                source="fake_poi_text",
            )

        def search_pois(self, anchor, categories, keywords=None, radius_meters=3000, limit_per_category=8):
            return [
                make_amap_poi("陈添记西关老字号", POICategory.RESTAURANT, 1),
                make_amap_poi("东湖酒楼粤菜老字号", POICategory.RESTAURANT, 2),
                make_amap_poi("凤小馆顺德菜", POICategory.RESTAURANT, 3),
                make_amap_poi("珠影市三宫影城", POICategory.ENTERTAINMENT, 4),
            ]

        def route_segment(self, origin, destination, mode="步行+公交", city=None):
            return None

        def recent_errors(self):
            return []

    monkeypatch.setattr(api, "AMapClient", FakeAMapClient)
    client = TestClient(app)
    response = client.post(
        "/api/plan",
        json={
            "query": "我想在广州永庆坊附近逛3个小时，想喝点东西，有文化点和散步地方",
            "user_id": "guangzhou-no-restaurant-padding-user",
            "route_context": {"source": "xiaotuan", "city_hint": "广州", "anchor_text": "广州永庆坊"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["routes"] == []
    assert any("没有生成可执行路线" in conflict for conflict in payload["constraint_conflicts"])
    assert all(candidate["poi"]["district"] == "广州" for candidate in payload["candidates"])


def test_selected_pois_are_pinned_and_completed():
    client = TestClient(app)
    selected = [
        {
            "id": "test-fav-coffee",
            "name": "深大收藏咖啡",
            "category": "咖啡/茶饮",
            "address": "深圳大学附近",
            "district": "南山区",
            "latitude": 22.535,
            "longitude": 113.937,
            "rating": 4.6,
            "review_count": 120,
            "price_per_person": 42,
            "avg_wait_minutes": 5,
            "business_hours": {"open": "09:00", "close": "22:00"},
            "tags": ["咖啡", "用户已选"],
            "ugc_summary": "收藏夹已选咖啡",
            "visit_duration_minutes": 40,
            "source": "context",
        },
        {
            "id": "test-fav-food",
            "name": "深大收藏轻食",
            "category": "餐饮",
            "address": "深圳大学附近",
            "district": "南山区",
            "latitude": 22.536,
            "longitude": 113.941,
            "rating": 4.5,
            "review_count": 360,
            "price_per_person": 78,
            "avg_wait_minutes": 12,
            "business_hours": {"open": "10:00", "close": "22:00"},
            "tags": ["轻食", "用户已选"],
            "ugc_summary": "收藏夹已选餐饮",
            "visit_duration_minutes": 60,
            "source": "context",
        },
    ]
    response = client.post(
        "/api/plan",
        json={
            "query": "把我收藏的深圳大学附近咖啡和轻食安排成3小时路线",
            "user_id": "pinned-poi-test-user",
            "route_context": {
                "source": "favorites",
                "city_hint": "深圳",
                "anchor_text": "深圳大学",
                "selected_pois": selected,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    names = [stop["poi"]["name"] for stop in payload["routes"][0]["route"]["stops"]]
    assert "深大收藏咖啡" in names
    assert "深大收藏轻食" in names
    assert len(names) >= 3


def test_amap_route_polyline_is_exposed_when_adapter_returns_segments(monkeypatch):
    class FakeAMapClient:
        enabled = True

        def resolve_anchor(self, text=None, city_hint=None, anchor_location=None):
            return api.AMapAnchor(
                text=text or "深圳大学",
                city="深圳",
                location=anchor_location or GeoPoint(latitude=22.53332, longitude=113.93646),
                source="fake",
            )

        def search_pois(self, anchor, categories, keywords=None, radius_meters=3000, limit_per_category=8):
            return api.fallback_pois_around_anchor(anchor, categories, count_per_category=1)

        def route_segment(self, origin, destination, mode="步行+公交"):
            return api.AMapRouteSegment(
                origin_id=origin.id,
                destination_id=destination.id,
                mode="walking",
                distance_meters=800,
                duration_minutes=10,
                polyline=[[origin.longitude, origin.latitude], [destination.longitude, destination.latitude]],
                source="amap_direction",
            )

    monkeypatch.setattr(api, "AMapClient", FakeAMapClient)
    client = TestClient(app)
    response = client.post(
        "/api/plan",
        json={
            "query": "深圳大学附近玩3小时",
            "user_id": "amap-polyline-test-user",
            "route_context": {"source": "xiaotuan", "city_hint": "深圳", "anchor_text": "深圳大学"},
        },
    )

    assert response.status_code == 200
    route = response.json()["routes"][0]["route"]
    assert route["map_polyline"]
    assert route["transit_segments"]
    assert route["transit_segments"][0]["source"] == "amap_direction"


def test_transport_strategy_from_route_context_is_used(monkeypatch):
    class FakeAMapClient:
        enabled = True

        def resolve_anchor(self, text=None, city_hint=None, anchor_location=None):
            return api.AMapAnchor(
                text=text or "深圳大学",
                city="深圳",
                location=GeoPoint(latitude=22.53332, longitude=113.93646),
                source="fake",
            )

        def search_pois(self, anchor, categories, keywords=None, radius_meters=3000, limit_per_category=8):
            return api.fallback_pois_around_anchor(anchor, categories, count_per_category=1)

        def route_segment(self, origin, destination, mode="步行+公交"):
            return None

    monkeypatch.setattr(api, "AMapClient", FakeAMapClient)
    client = TestClient(app)
    response = client.post(
        "/api/plan",
        json={
            "query": "深圳大学附近玩3小时，少走路",
            "user_id": "transport-strategy-test-user",
            "route_context": {
                "source": "xiaotuan",
                "city_hint": "深圳",
                "anchor_text": "深圳大学",
                "transport_strategy": "打车优先",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"]["constraints"]["transport_mode"] == "打车优先"
    assert payload["routes"][0]["route"]["transit_segments"][0]["strategy"] == "打车优先"


def test_intent_parser_uses_mocked_llm_when_key_is_configured(monkeypatch):
    def fake_llm(self, user_input, rules_intent, conversation_history=None, user_profile=None):
        constraints = rules_intent.constraints.model_copy(update={
            "city": "深圳",
            "total_time_hours": 2.5,
            "transport_mode": "打车优先",
        })
        return rules_intent.model_copy(update={
            "city": "深圳",
            "constraints": constraints,
            "parser_source": "llm",
            "parser_confidence": 0.93,
            "parser_reason": "mocked DeepSeek parser",
            "llm_slots": {"anchor_text": "深圳大学", "transport_mode": "打车优先"},
            "extracted_preferences": {
                **rules_intent.extracted_preferences,
                "anchor_text": "深圳大学",
                "intent_parser_source": "llm",
            },
        })

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(IntentParserAgent, "_parse_with_llm", fake_llm)
    load_agents.cache_clear()
    client = TestClient(app)
    response = client.post(
        "/api/plan",
        json={"query": "深圳大学附近玩两个半小时，打车优先", "user_id": "mock-llm-parser-user"},
    )
    load_agents.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"]["parser_source"] == "llm"
    assert payload["intent"]["parser_confidence"] == 0.93
    assert payload["intent"]["constraints"]["transport_mode"] == "打车优先"


def test_profile_modes_change_route_context_or_result():
    client = TestClient(app)
    query = "我下午要去外滩玩3个小时，帮我规划一个路线"
    low_wait = client.post(
        "/api/plan",
        json={"query": query, "user_id": "profile-low-test", "profile_mode": "低排队务实型"},
    ).json()
    artsy = client.post(
        "/api/plan",
        json={"query": query, "user_id": "profile-art-test", "profile_mode": "文艺体验型"},
    ).json()

    assert low_wait["meituan_user_context"]["max_wait_preference"] < artsy["meituan_user_context"]["max_wait_preference"]
    assert low_wait["profile_influence"] != artsy["profile_influence"]
    low_ids = [stop["poi"]["id"] for stop in low_wait["routes"][0]["route"]["stops"]]
    art_ids = [stop["poi"]["id"] for stop in artsy["routes"][0]["route"]["stops"]]
    assert low_ids != art_ids or low_wait["routes"][0]["route"]["total_wait_minutes"] <= artsy["routes"][0]["route"]["total_wait_minutes"]


def test_profile_sources_and_manual_import_drive_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "PROFILE_IMPORTS_PATH", tmp_path / "profile_imports.json")
    client = TestClient(app)
    import_response = client.post(
        "/api/profile/import",
        json={
            "profile_id": "pytest-imported-profile",
            "display_name": "Pytest 脱敏样本",
            "recent_searches": ["少走路", "室内咖啡", "外滩展览"],
            "favorite_pois": ["安静咖啡", "海派光影展馆"],
            "browsed_pois": ["雨天可去", "拍照出片"],
            "favorite_categories": ["咖啡/茶饮", "景点"],
            "favorite_districts": ["黄浦区"],
            "frequent_districts": ["黄浦区"],
            "budget_preference": 260,
            "max_wait_preference": 8,
            "walk_preference": "少走路",
            "coupon_sensitive": False,
        },
    )

    assert import_response.status_code == 200
    imported = import_response.json()
    assert imported["profile"]["profile_id"] == "pytest-imported-profile"
    assert imported["context"]["profile_mode"] == "Pytest 脱敏样本"

    sources = client.get("/api/profile-sources")
    assert sources.status_code == 200
    manual_profiles = [
        profile
        for source in sources.json()["sources"]
        if source["source"] == "manual_import"
        for profile in source["profiles"]
    ]
    assert any(profile["profile_id"] == "pytest-imported-profile" for profile in manual_profiles)

    query = "我下午要去外滩玩3个小时，帮我规划一个路线"
    manual_plan = client.post(
        "/api/plan",
        json={
            "query": query,
            "user_id": "manual-import-plan-user",
            "profile_source": "manual_import",
            "profile_id": "pytest-imported-profile",
        },
    ).json()
    preset_plan = client.post(
        "/api/plan",
        json={"query": query, "user_id": "preset-plan-user", "profile_mode": "文艺体验型"},
    ).json()

    assert manual_plan["profile_source"] == "manual_import"
    assert manual_plan["profile_id"] == "pytest-imported-profile"
    assert "脱敏导入" in manual_plan["profile_source_description"]
    assert manual_plan["meituan_user_context"]["max_wait_preference"] == 8
    assert manual_plan["profile_influence"] != preset_plan["profile_influence"]


def test_judge_session_profile_is_labeled_as_instant_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "PROFILE_IMPORTS_PATH", tmp_path / "profile_imports.json")
    client = TestClient(app)
    import_response = client.post(
        "/api/profile/import",
        json={
            "profile_id": "judge-session",
            "display_name": "评委即时画像",
            "recent_searches": ["深圳大学", "展览文化", "带爸妈"],
            "favorite_pois": ["深圳大学附近展览文化"],
            "browsed_pois": ["少走路", "尽量不排队"],
            "favorite_categories": ["景点", "咖啡/茶饮"],
            "favorite_districts": ["深圳"],
            "frequent_districts": ["深圳"],
            "budget_preference": 260,
            "max_wait_preference": 8,
            "walk_preference": "少走路",
            "coupon_sensitive": False,
        },
    )

    assert import_response.status_code == 200
    assert "评委即时画像" in import_response.json()["profile"]["summary"]

    plan_response = client.post(
        "/api/plan",
        json={
            "query": "深圳大学附近玩3小时",
            "user_id": "judge-session-user",
            "profile_source": "manual_import",
            "profile_id": "judge-session",
            "route_context": {"source": "xiaotuan", "city_hint": "深圳", "anchor_text": "深圳大学"},
        },
    )
    payload = plan_response.json()
    assert payload["profile_id"] == "judge-session"
    assert "评委即时画像" in payload["profile_source_description"]


def test_profile_import_rejects_sensitive_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "PROFILE_IMPORTS_PATH", tmp_path / "profile_imports.json")
    client = TestClient(app)
    response = client.post(
        "/api/profile/import",
        json={
            "display_name": "Bad Profile",
            "recent_searches": ["咖啡", "外滩", "展览"],
            "phone": "13800000000",
        },
    )

    assert response.status_code == 400
    assert "禁止字段" in response.json()["detail"]


def test_adjust_api_updates_route_with_explanation():
    client = TestClient(app)
    query = "帮我规划一个上海外滩附近的文艺下午，时间3小时，两个人，预算200，不想排队"
    plan_payload = client.post(
        "/api/plan",
        json={"query": query, "user_id": "adjust-test-user", "profile_mode": "文艺体验型"},
    ).json()
    route = plan_payload["routes"][0]["route"]

    adjust_response = client.post(
        "/api/adjust",
        json={
            "query": query,
            "instruction": "不要排队",
            "route": route,
            "user_id": "adjust-test-user",
            "profile_mode": "低排队务实型",
        },
    )

    assert adjust_response.status_code == 200
    payload = adjust_response.json()
    assert payload["route"]["route"]["stops"]
    assert payload["adjustment_summary"]
    assert payload["adjustment_status"] in {"applied", "partial", "not_applied"}
    assert payload["before_metrics"]["stop_count"] >= 3
    assert payload["after_metrics"]["stop_count"] >= 3
    assert "total_wait_minutes" in payload["metric_deltas"]
    assert "changed_stops" in payload
    assert "suggested_relaxations" in payload
    assert payload["follow_up"]["options"]
    assert payload["planning_time_ms"] >= 0
    assert payload["route_completeness"]["is_complete"] is True
    assert payload["tool_trace"]
    assert [step["tool"] for step in payload["tool_trace"]][:2] == ["ParseAdjustment", "SearchReplacementPOI"]


def test_adjust_api_does_not_fake_improvement_when_no_better_option():
    client = TestClient(app)
    query = "帮我规划一个上海外滩附近的文艺下午，时间3小时，两个人，预算200，不想排队"
    plan_payload = client.post(
        "/api/plan",
        json={"query": query, "user_id": "adjust-noop-test-user", "profile_mode": "低排队务实型"},
    ).json()
    route = plan_payload["routes"][0]["route"]
    route["total_wait_minutes"] = 0
    for stop in route["stops"]:
        stop["wait_minutes"] = 0
        stop["poi"]["avg_wait_minutes"] = 0

    adjust_response = client.post(
        "/api/adjust",
        json={
            "query": query,
            "instruction": "不要排队",
            "route": route,
            "user_id": "adjust-noop-test-user",
            "profile_mode": "低排队务实型",
        },
    )

    assert adjust_response.status_code == 200
    payload = adjust_response.json()
    assert payload["adjustment_status"] == "not_applied"
    assert payload["metric_deltas"]["total_wait_minutes"] == 0
    assert payload["suggested_relaxations"]


def test_adjust_api_repairs_too_many_cafes(monkeypatch):
    monkeypatch.setattr(api, "classify_adjustment_with_deepseek", lambda *_args, **_kwargs: None)

    def make_candidate(name, category, index, price=50, rating=4.6):
        data = make_adjust_test_poi(name, category, index, price=price, rating=rating)
        return POI(**data)

    class FakeAMapClient:
        enabled = True

        def resolve_anchor(self, text=None, city_hint=None, anchor_location=None):
            return api.AMapAnchor(
                text=text or "广州永庆坊",
                city="广州",
                location=GeoPoint(latitude=23.114, longitude=113.25),
                source="fake_poi_text",
            )

        def search_pois(self, anchor, categories, keywords=None, radius_meters=3000, limit_per_category=8):
            return [
                make_candidate("粤剧艺术博物馆", POICategory.ATTRACTION, 20, price=20, rating=4.8),
                make_candidate("荔湾湖公园散步点", POICategory.SHOPPING, 21, price=10, rating=4.7),
                make_candidate("珠影市三宫影城", POICategory.ENTERTAINMENT, 22, price=55, rating=4.6),
                make_candidate("西关粤菜小馆", POICategory.RESTAURANT, 23, price=88, rating=4.5),
            ]

        def route_segment(self, origin, destination, mode="步行+公交", city=None):
            return None

        def recent_errors(self):
            return []

    monkeypatch.setattr(api, "AMapClient", FakeAMapClient)
    client = TestClient(app)
    current_pois = [
        make_adjust_test_poi("红门咖啡", POICategory.CAFE, 1, price=42, rating=4.6),
        make_adjust_test_poi("永庆坊", POICategory.ATTRACTION, 2, price=0, rating=4.8),
        make_adjust_test_poi("CAFE FLOWERYARDS", POICategory.CAFE, 3, price=48, rating=4.5),
        make_adjust_test_poi("西关84 History Art Cafe", POICategory.CAFE, 4, price=52, rating=4.5),
    ]

    response = client.post(
        "/api/adjust",
        json={
            "query": "广州永庆坊附近逛吃5小时，用户画像偏向咖啡店",
            "instruction": "不要这么多咖啡，换成更适合散步的点",
            "route": make_adjust_test_route(current_pois),
            "user_id": "adjust-too-many-cafes-user",
            "profile_mode": "文艺体验型",
            "route_context": {"source": "xiaotuan", "city_hint": "广州", "anchor_text": "广州永庆坊"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    categories = [stop["poi"]["category"] for stop in payload["route"]["route"]["stops"]]
    assert payload["adjustment_status"] in {"applied", "partial"}
    assert categories.count("咖啡/茶饮") <= 1
    assert any(category in {"景点", "娱乐", "购物"} for category in categories)
    assert payload["changed_stops"]
    assert "kind=focus" in payload["tool_trace"][0]["output"]


def test_route_intent_rules_fallback(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    load_agents.cache_clear()
    client = TestClient(app)

    high = client.post("/api/route-intent", json={"query": "我下午要去外滩玩3个小时", "source": "xiaotuan"})
    known_landmark = client.post("/api/route-intent", json={"query": "万象天地玩3小时", "source": "xiaotuan"})
    arbitrary_anchor = client.post("/api/route-intent", json={"query": "三里屯逛2小时", "source": "xiaotuan"})
    family = client.post("/api/route-intent", json={"query": "带爸妈在金鱼胡同轻松逛半天", "source": "xiaotuan"})
    multi_activity = client.post("/api/route-intent", json={"query": "今晚三里屯吃饭再看电影", "source": "xiaotuan"})
    mixed = client.post("/api/route-intent", json={"query": "万象天地逛吃一下安排3小时", "source": "xiaotuan"})
    medium = client.post("/api/route-intent", json={"query": "外滩下午有什么好玩的", "source": "xiaotuan"})
    medium_landmark = client.post("/api/route-intent", json={"query": "万象天地有什么好玩的", "source": "xiaotuan"})
    missing_location = client.post("/api/route-intent", json={"query": "今晚想吃饭再找个地方散步，不想排队", "source": "xiaotuan"})
    low = client.post("/api/route-intent", json={"query": "这家店电话是多少", "source": "xiaotuan"})
    low_hours = client.post("/api/route-intent", json={"query": "gaga营业到几点", "source": "xiaotuan"})
    low_coupon = client.post("/api/route-intent", json={"query": "有没有优惠券", "source": "xiaotuan"})
    low_menu = client.post("/api/route-intent", json={"query": "菜单有什么推荐", "source": "xiaotuan"})

    assert high.status_code == 200
    assert high.json()["action"] == "open_plugin"
    assert high.json()["source"] == "rules"
    assert known_landmark.json()["action"] == "open_plugin"
    assert known_landmark.json()["detected_slots"]["location"] == "万象天地"
    assert arbitrary_anchor.json()["action"] == "open_plugin"
    assert arbitrary_anchor.json()["detected_slots"]["location"] == "三里屯"
    assert family.json()["action"] == "open_plugin"
    assert family.json()["detected_slots"]["location"] == "金鱼胡同"
    assert multi_activity.json()["action"] == "open_plugin"
    assert mixed.json()["action"] == "open_plugin"
    assert medium.json()["action"] == "ask_confirm"
    assert medium_landmark.json()["action"] == "ask_confirm"
    assert medium_landmark.json()["detected_slots"]["location"] == "万象天地"
    assert missing_location.json()["action"] == "ask_confirm"
    assert "地点/区域" in missing_location.json()["detected_slots"]["missing_slots"]
    assert low.json()["action"] == "normal_answer"
    assert low_hours.json()["action"] == "normal_answer"
    assert low_coupon.json()["action"] == "normal_answer"
    assert low_menu.json()["action"] == "normal_answer"


def test_route_intent_multi_turn_slot_completion(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    load_agents.cache_clear()
    client = TestClient(app)

    first = client.post(
        "/api/route-intent",
        json={"query": "今晚想吃饭再找个地方散步，不想排队", "source": "xiaotuan"},
    )

    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["action"] == "ask_confirm"
    assert first_payload["turn_state"] == "collecting_slots"
    assert first_payload["missing_slots"] == ["location"]
    assert first_payload["clarification_question"] == "想在哪个区域安排？"

    second = client.post(
        "/api/route-intent",
        json={
            "query": "深圳大学附近，3小时",
            "source": "xiaotuan",
            "conversation_id": first_payload["conversation_id"],
            "previous_intent": first_payload,
        },
    )

    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["action"] == "open_plugin"
    assert second_payload["turn_state"] == "ready_to_plan"
    assert second_payload["missing_slots"] == []
    assert second_payload["filled_slots"]["location"] == "深圳大学"
    assert second_payload["filled_slots"]["time"] == "3小时"
    assert "餐饮" in second_payload["filled_slots"]["activities"]
    assert "景点" in second_payload["filled_slots"]["activities"]
    assert "深圳大学" in second_payload["merged_query"]
    assert "3小时" in second_payload["merged_query"]


def test_route_intent_context_does_not_repeat_location_question(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    load_agents.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/api/route-intent",
        json={
            "query": "安排晚饭前后顺路可逛的路线，少走路",
            "source": "poi_detail",
            "context": {"anchor_text": "gaga金地威新中心店", "current_city": "深圳"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "location" not in payload["missing_slots"]
    assert payload["filled_slots"]["location"] == "gaga金地威新中心店"


def test_feedback_api_updates_profile():
    client = TestClient(app)
    plan_response = client.post(
        "/api/plan",
        json={
            "query": "想吃上海特色，但不想排队超过15分钟，4个人，晚上6点出发",
            "user_id": "feedback-test-user",
        },
    )
    route = plan_response.json()["routes"][0]["route"]

    feedback_response = client.post(
        "/api/feedback",
        json={"user_id": "feedback-test-user", "route": route, "feedback": 1},
    )

    assert feedback_response.status_code == 200
    assert feedback_response.json()["profile"]["liked_poi_ids"]


def test_replace_api_returns_same_category_options():
    client = TestClient(app)
    query = "帮我规划一个上海外滩附近的文艺下午，时间3小时，两个人，预算200，不想排队"
    plan_response = client.post(
        "/api/plan",
        json={"query": query, "user_id": "replace-test-user"},
    )
    route = plan_response.json()["routes"][0]["route"]
    first_stop = route["stops"][0]

    replace_response = client.post(
        "/api/replace",
        json={
            "query": query,
            "route": route,
            "stop_order": first_stop["order"],
            "user_id": "replace-test-user",
        },
    )

    assert replace_response.status_code == 200
    options = replace_response.json()["options"]
    assert options
    assert options[0]["poi"]["category"] == first_stop["poi"]["category"]


def test_replace_api_uses_current_stop_location_for_dynamic_options(monkeypatch):
    class FakeAMapClient:
        enabled = True

        def resolve_anchor(self, text=None, city_hint=None, anchor_location=None):
            assert anchor_location is not None
            assert anchor_location.latitude < 23
            assert 113 < anchor_location.longitude < 115
            return api.AMapAnchor(
                text=text or "原石牛扒(中心书城店)",
                city=city_hint or "深圳",
                location=anchor_location,
                source="context_location",
            )

        def search_pois(self, anchor, categories, keywords=None, radius_meters=3000, limit_per_category=8):
            assert anchor.city in {"深圳", "福田区", "深圳市"}
            return [
                POI(
                    id="amap-shenzhen-steak-replace",
                    name="深圳同类牛扒替换店",
                    category=POICategory.RESTAURANT,
                    address="深圳市福田区中心书城附近",
                    district="福田区",
                    latitude=22.545,
                    longitude=114.061,
                    rating=4.6,
                    review_count=320,
                    price_per_person=108,
                    avg_wait_minutes=6,
                    business_hours={"open": "10:30", "close": "22:00"},
                    tags=["餐饮", "牛扒", "高德POI"],
                    ugc_summary="深圳当前站点附近同类替换。",
                    visit_duration_minutes=60,
                    source="amap",
                    external_id="fake-shenzhen-steak",
                    distance_from_anchor_meters=360,
                )
            ]

    monkeypatch.setattr(api, "AMapClient", FakeAMapClient)
    client = TestClient(app)
    route = {
        "id": "replace-location-test-route",
        "title": "福田文艺紧凑不绕路",
        "description": "深圳路线",
        "stops": [
            {
                "order": 1,
                "poi": {
                    "id": "amap-current-steak",
                    "name": "原石牛扒(中心书城店)",
                    "category": "餐饮",
                    "address": "深圳市福田区中心书城",
                    "district": "福田区",
                    "latitude": 22.5431,
                    "longitude": 114.0596,
                    "rating": 4.5,
                    "review_count": 500,
                    "price_per_person": 120,
                    "avg_wait_minutes": 8,
                    "business_hours": {"open": "10:30", "close": "22:00"},
                    "tags": ["餐饮", "高德POI"],
                    "ugc_summary": "当前深圳站点",
                    "visit_duration_minutes": 60,
                    "source": "amap",
                    "external_id": "fake-current-steak",
                    "distance_from_anchor_meters": 0,
                },
                "arrival_time": "14:00",
                "departure_time": "15:08",
                "duration_minutes": 60,
                "wait_minutes": 8,
                "transit_to_next": "步行约 6 分钟",
                "transit_minutes": 6,
                "transit_polyline": [],
                "tips": "",
            },
            {
                "order": 2,
                "poi": {
                    "id": "amap-shenzhen-culture",
                    "name": "深圳中心书城",
                    "category": "景点",
                    "address": "深圳市福田区",
                    "district": "福田区",
                    "latitude": 22.5419,
                    "longitude": 114.0601,
                    "rating": 4.6,
                    "review_count": 800,
                    "price_per_person": 0,
                    "avg_wait_minutes": 3,
                    "business_hours": {"open": "10:00", "close": "22:00"},
                    "tags": ["景点"],
                    "ugc_summary": "当前路线文化站",
                    "visit_duration_minutes": 60,
                    "source": "amap",
                },
                "arrival_time": "15:14",
                "departure_time": "16:22",
                "duration_minutes": 60,
                "wait_minutes": 3,
                "transit_to_next": None,
                "transit_minutes": None,
                "transit_polyline": [],
                "tips": "",
            },
        ],
        "total_time_minutes": 142,
        "total_cost_per_person": 120,
        "total_wait_minutes": 11,
        "total_transit_minutes": 6,
        "map_polyline": [],
        "transit_segments": [],
        "highlights": [],
        "warnings": [],
    }

    response = client.post(
        "/api/replace",
        json={
            "query": "我下午要去深圳福田中心书城附近玩3个小时",
            "route": route,
            "stop_order": 1,
            "user_id": "replace-location-test-user",
            "route_context": {
                "source": "replace",
                "city_hint": "深圳",
                "anchor_text": "原石牛扒(中心书城店)",
                "anchor_location": {"latitude": 22.5431, "longitude": 114.0596},
            },
        },
    )

    assert response.status_code == 200
    options = response.json()["options"]
    assert options
    assert options[0]["poi"]["name"] == "深圳同类牛扒替换店"
    assert options[0]["poi"]["district"] == "福田区"
    assert options[0]["poi"]["source"] == "amap"
