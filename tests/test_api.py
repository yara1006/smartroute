from fastapi.testclient import TestClient

import api
from api import app, load_agents
from core.models import GeoPoint


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
    assert "餐饮+文化/娱乐覆盖" in hits


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


def test_shenzhen_anchor_uses_dynamic_location_without_amap_key(monkeypatch):
    monkeypatch.delenv("AMAP_WEB_SERVICE_KEY", raising=False)
    client = TestClient(app)
    response = client.post(
        "/api/plan",
        json={
            "query": "我下午要去深圳大学附近玩3个小时，帮我规划一个路线",
            "user_id": "shenzhen-anchor-test-user",
            "route_context": {
                "source": "xiaotuan",
                "city_hint": "深圳",
                "anchor_text": "深圳大学",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    route = payload["routes"][0]["route"]
    assert payload["intent"]["city"] == "深圳"
    assert payload["intent"]["extracted_preferences"]["anchor_text"] == "深圳大学"
    assert len(route["stops"]) >= 3
    assert route["stops"][0]["poi"]["latitude"] < 23
    assert route["stops"][0]["poi"]["longitude"] < 114.5
    assert any("高德 POI" in item for item in payload["trace"])


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


def test_route_intent_rules_fallback(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    load_agents.cache_clear()
    client = TestClient(app)

    high = client.post("/api/route-intent", json={"query": "我下午要去外滩玩3个小时", "source": "xiaotuan"})
    medium = client.post("/api/route-intent", json={"query": "外滩下午有什么好玩的", "source": "xiaotuan"})
    low = client.post("/api/route-intent", json={"query": "这家店电话是多少", "source": "xiaotuan"})

    assert high.status_code == 200
    assert high.json()["action"] == "open_plugin"
    assert high.json()["source"] == "rules"
    assert medium.json()["action"] == "ask_confirm"
    assert low.json()["action"] == "normal_answer"


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
