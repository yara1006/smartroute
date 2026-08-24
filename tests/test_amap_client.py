import json

from core.models import GeoPoint, POICategory
from core.services.amap_client import AMapAnchor, AMapClient


def amap_item(item_id, name, location, poi_type, typecode):
    return {
        "id": item_id,
        "name": name,
        "address": "广州市荔湾区永庆坊附近",
        "location": location,
        "type": poi_type,
        "typecode": typecode,
        "adname": "荔湾区",
        "cityname": "广州市",
        "business": {"rating": "4.6", "cost": "45", "rating_count": "120"},
    }


def test_amap_search_uses_text_fallback_when_around_hits_daily_limit(monkeypatch):
    anchor = AMapAnchor(
        text="广州永庆坊",
        city="广州",
        location=GeoPoint(latitude=23.114821, longitude=113.237495),
        source="amap_poi_text",
    )
    client = AMapClient(key="test-key")

    def fake_get(path, params):
        if path == "/v5/place/around":
            raise RuntimeError("USER_DAILY_QUERY_OVER_LIMIT")
        assert path == "/v5/place/text"
        types = params.get("types")
        if types == "050500":
            return {
                "pois": [
                    amap_item("cafe-1", "急急脚咖啡公司(永庆坊店)", "113.237833,23.115253", "餐饮服务;咖啡厅;咖啡厅", "050500")
                ]
            }
        if types == "110000|140000":
            return {
                "pois": [
                    amap_item("culture-1", "粤剧艺术博物馆", "113.240275,23.116383", "风景名胜;博物馆;博物馆", "140000")
                ]
            }
        if types == "060000":
            return {
                "pois": [
                    amap_item("walk-1", "永庆坊", "113.237495,23.114821", "购物服务;特色商业街;特色商业街", "060000")
                ]
            }
        return {"pois": []}

    monkeypatch.setattr(client, "_get", fake_get)

    pois = client.search_pois(
        anchor,
        [POICategory.CAFE, POICategory.ATTRACTION, POICategory.SHOPPING],
        keywords=["喝点东西", "文化", "散步"],
        radius_meters=3000,
        limit_per_category=3,
    )

    categories = {poi.category for poi in pois}
    assert categories == {POICategory.CAFE, POICategory.ATTRACTION, POICategory.SHOPPING}
    assert all(poi.source == "amap" for poi in pois)
    assert all((poi.distance_from_anchor_meters or 0) <= 3000 for poi in pois)
    assert any("place/around" in error for error in client.recent_errors())


def test_amap_get_caches_identical_requests(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"status": "1", "infocode": "10000", "pois": []}).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = AMapClient(key="cache-test-key")

    first = client._get("/v5/place/text", {"keywords": "广州永庆坊", "region": "广州"})
    second = client._get("/v5/place/text", {"region": "广州", "keywords": "广州永庆坊"})

    assert first == second
    assert calls["count"] == 1
