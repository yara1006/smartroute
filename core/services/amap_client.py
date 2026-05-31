from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from core.models import GeoPoint, POI, POICategory
from core.rag.vector_store import haversine_km


AMAP_REST_BASE = "https://restapi.amap.com"
DEFAULT_RADIUS_METERS = 3000

KNOWN_ANCHORS: dict[str, tuple[str, GeoPoint]] = {
    "深圳大学": ("深圳", GeoPoint(latitude=22.53332, longitude=113.93646)),
    "深大": ("深圳", GeoPoint(latitude=22.53332, longitude=113.93646)),
    "科技园": ("深圳", GeoPoint(latitude=22.54075, longitude=113.94483)),
    "深圳湾": ("深圳", GeoPoint(latitude=22.50676, longitude=113.94537)),
    "金地威新中心": ("深圳", GeoPoint(latitude=22.53461, longitude=113.94016)),
    "gaga金地威新中心店": ("深圳", GeoPoint(latitude=22.53461, longitude=113.94016)),
    "gaga": ("深圳", GeoPoint(latitude=22.53461, longitude=113.94016)),
    "外滩": ("上海", GeoPoint(latitude=31.23969, longitude=121.49976)),
    "南京东路": ("上海", GeoPoint(latitude=31.23516, longitude=121.47764)),
    "陆家嘴": ("上海", GeoPoint(latitude=31.23965, longitude=121.50739)),
    "静安寺": ("上海", GeoPoint(latitude=31.22309, longitude=121.44524)),
}

CATEGORY_TYPE_CODES: dict[POICategory, str] = {
    POICategory.RESTAURANT: "050000",
    POICategory.CAFE: "050500",
    POICategory.ATTRACTION: "110000|140000",
    POICategory.ENTERTAINMENT: "080000",
    POICategory.SHOPPING: "060000",
    POICategory.ACCOMMODATION: "100000",
}

FALLBACK_NAME_BANK: dict[POICategory, list[str]] = {
    POICategory.RESTAURANT: ["城市小馆", "本地风味餐厅", "轻食厨房", "顺路小吃集合"],
    POICategory.CAFE: ["街角咖啡", "安静茶饮空间", "设计感咖啡", "休息补给站"],
    POICategory.ATTRACTION: ["城市展览空间", "街区文化点", "地标步行打卡点", "公共艺术空间"],
    POICategory.ENTERTAINMENT: ["轻娱乐空间", "夜游体验点", "演出活动点", "室内娱乐站"],
    POICategory.SHOPPING: ["生活方式买手店", "室内商场", "街区市集", "文创集合店"],
}


@dataclass
class AMapRouteSegment:
    origin_id: str
    destination_id: str
    mode: str
    distance_meters: int
    duration_minutes: int
    polyline: list[list[float]]
    source: str


@dataclass
class AMapAnchor:
    text: str
    city: str
    location: GeoPoint
    source: str


class AMapClient:
    """Small adapter around AMap Web Service.

    The adapter deliberately returns normalized app models and keeps network
    errors non-fatal so SmartRoute can downgrade to local demo data.
    """

    def __init__(self, key: str | None = None, timeout: float = 3.0) -> None:
        self.key = (key if key is not None else os.getenv("AMAP_WEB_SERVICE_KEY", "")).strip()
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def resolve_anchor(
        self,
        text: str | None,
        city_hint: str | None = None,
        anchor_location: GeoPoint | None = None,
    ) -> AMapAnchor | None:
        clean_text = (text or "").strip()
        if anchor_location:
            return AMapAnchor(
                text=clean_text or "当前位置",
                city=normalize_city_hint(city_hint) or "未知城市",
                location=anchor_location,
                source="context_location",
            )

        known = resolve_known_anchor(clean_text)
        if known:
            city, location = known
            return AMapAnchor(text=clean_text, city=normalize_city_hint(city_hint) or city, location=location, source="known_anchor")

        if not clean_text:
            return None

        if self.enabled:
            try:
                payload = self._get(
                    "/v3/geocode/geo",
                    {
                        "address": clean_text,
                        "city": normalize_city_hint(city_hint) or "",
                        "output": "JSON",
                    },
                )
                geocodes = payload.get("geocodes") or []
                if geocodes:
                    first = geocodes[0]
                    location = parse_location(first.get("location"))
                    if location:
                        city = normalize_city_hint(str(first.get("city") or city_hint or ""))
                        return AMapAnchor(text=clean_text, city=city or "未知城市", location=location, source="amap_geocode")
            except Exception:
                return None
        return None

    def search_pois(
        self,
        anchor: AMapAnchor,
        categories: list[POICategory],
        keywords: list[str] | None = None,
        radius_meters: int = DEFAULT_RADIUS_METERS,
        limit_per_category: int = 8,
    ) -> list[POI]:
        if not self.enabled:
            return []

        pois: list[POI] = []
        seen: set[str] = set()
        terms = [item for item in keywords or [] if item.strip()]

        for category in categories:
            type_codes = CATEGORY_TYPE_CODES.get(category, "")
            query_terms = terms or keywords_for_category(category)
            for keyword in query_terms[:3]:
                try:
                    payload = self._get(
                        "/v5/place/around",
                        {
                            "keywords": keyword,
                            "types": type_codes,
                            "location": f"{anchor.location.longitude},{anchor.location.latitude}",
                            "radius": str(radius_meters),
                            "region": anchor.city if anchor.city != "未知城市" else "",
                            "show_fields": "business,photos",
                            "page_size": str(limit_per_category),
                        },
                    )
                    items = payload.get("pois") or []
                    for item in items:
                        poi = poi_from_amap(item, category, anchor)
                        if not poi or poi.id in seen:
                            continue
                        seen.add(poi.id)
                        pois.append(poi)
                except Exception:
                    continue
        return sort_by_anchor_distance(pois)

    def route_segment(self, origin: POI, destination: POI, mode: str = "步行+公交") -> AMapRouteSegment | None:
        if not self.enabled:
            return None
        api_mode = "driving" if "打车" in mode or "驾车" in mode else "walking"
        path = "/v3/direction/driving" if api_mode == "driving" else "/v3/direction/walking"
        try:
            payload = self._get(
                path,
                {
                    "origin": f"{origin.longitude},{origin.latitude}",
                    "destination": f"{destination.longitude},{destination.latitude}",
                    "extensions": "base",
                    "output": "JSON",
                },
            )
            route = payload.get("route") or {}
            paths = route.get("paths") or []
            if not paths:
                return None
            first = paths[0]
            duration_seconds = int(float(first.get("duration") or 0))
            distance_meters = int(float(first.get("distance") or 0))
            polyline = []
            for step in first.get("steps") or []:
                polyline.extend(parse_polyline(step.get("polyline") or ""))
            if not polyline:
                polyline = [[origin.longitude, origin.latitude], [destination.longitude, destination.latitude]]
            return AMapRouteSegment(
                origin_id=origin.id,
                destination_id=destination.id,
                mode=api_mode,
                distance_meters=distance_meters,
                duration_minutes=max(1, math.ceil(duration_seconds / 60)),
                polyline=dedupe_polyline(polyline),
                source="amap_direction",
            )
        except Exception:
            return None

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        query = {key: value for key, value in params.items() if value not in (None, "")}
        query["key"] = self.key
        url = f"{AMAP_REST_BASE}{path}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(url, headers={"User-Agent": "SmartRoute-Demo/1.0"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        status = str(payload.get("status", "1"))
        infocode = str(payload.get("infocode", "10000"))
        if status != "1" and infocode != "10000":
            raise RuntimeError(payload.get("info") or "AMap request failed")
        return payload


def normalize_city_hint(city: str | None) -> str | None:
    if not city:
        return None
    value = str(city).strip()
    if not value:
        return None
    if "深圳" in value:
        return "深圳"
    if "上海" in value:
        return "上海"
    if "广州" in value:
        return "广州"
    if "北京" in value:
        return "北京"
    return value.replace("市", "")


def resolve_known_anchor(text: str | None) -> tuple[str, GeoPoint] | None:
    value = (text or "").replace(" ", "")
    if not value:
        return None
    for key, payload in KNOWN_ANCHORS.items():
        if key in value:
            return payload
    return None


def parse_location(value: str | None) -> GeoPoint | None:
    if not value or "," not in value:
        return None
    lng_text, lat_text = value.split(",", 1)
    try:
        return GeoPoint(latitude=float(lat_text), longitude=float(lng_text))
    except ValueError:
        return None


def parse_polyline(value: str) -> list[list[float]]:
    points: list[list[float]] = []
    for pair in value.split(";"):
        if "," not in pair:
            continue
        lng_text, lat_text = pair.split(",", 1)
        try:
            points.append([float(lng_text), float(lat_text)])
        except ValueError:
            continue
    return points


def dedupe_polyline(points: list[list[float]]) -> list[list[float]]:
    deduped: list[list[float]] = []
    previous: tuple[float, float] | None = None
    for lng, lat in points:
        current = (round(lng, 6), round(lat, 6))
        if current == previous:
            continue
        deduped.append([lng, lat])
        previous = current
    return deduped


def poi_from_amap(item: dict[str, Any], category: POICategory, anchor: AMapAnchor) -> POI | None:
    location = parse_location(item.get("location"))
    if not location:
        return None
    business = item.get("business") if isinstance(item.get("business"), dict) else {}
    rating = parse_float(business.get("rating"), 4.4)
    price = parse_float(business.get("cost"), default_price(category))
    distance = parse_int(item.get("distance"), None)
    tags = [category.value]
    type_name = str(item.get("type") or "")
    if type_name:
        tags.extend([part for part in type_name.split(";") if part][:2])
    return POI(
        id=f"amap-{item.get('id') or stable_token(item.get('name', ''), location.longitude, location.latitude)}",
        external_id=str(item.get("id") or ""),
        name=str(item.get("name") or "高德 POI"),
        category=category,
        address=str(item.get("address") or ""),
        district=str(item.get("adname") or anchor.city),
        latitude=location.latitude,
        longitude=location.longitude,
        rating=max(3.8, min(5.0, rating)),
        review_count=max(0, parse_int(business.get("rating_count"), 0) or 0),
        price_per_person=max(0, price),
        avg_wait_minutes=estimated_wait(category, rating, distance),
        business_hours={"open": "10:00", "close": "22:00"},
        tags=list(dict.fromkeys(tags))[:6],
        ugc_summary=f"来自高德周边搜索，距{anchor.text or '锚点'}约 {distance or 0} 米，适合作为路线候选。",
        visit_duration_minutes=default_duration(category),
        source="amap",
        distance_from_anchor_meters=distance,
    )


def sort_by_anchor_distance(pois: list[POI]) -> list[POI]:
    return sorted(
        pois,
        key=lambda poi: (
            poi.distance_from_anchor_meters if poi.distance_from_anchor_meters is not None else 999999,
            -poi.rating,
            poi.avg_wait_minutes,
        ),
    )


def keywords_for_category(category: POICategory) -> list[str]:
    return {
        POICategory.RESTAURANT: ["美食", "餐厅", "特色菜"],
        POICategory.CAFE: ["咖啡", "下午茶", "茶饮"],
        POICategory.ATTRACTION: ["景点", "展览", "博物馆"],
        POICategory.ENTERTAINMENT: ["娱乐", "演出", "电影"],
        POICategory.SHOPPING: ["商场", "市集", "购物"],
        POICategory.ACCOMMODATION: ["酒店"],
    }.get(category, ["美食"])


def fallback_pois_around_anchor(anchor: AMapAnchor, categories: list[POICategory], count_per_category: int = 3) -> list[POI]:
    pois: list[POI] = []
    seen: set[str] = set()
    for category_index, category in enumerate(categories):
        names = FALLBACK_NAME_BANK.get(category, FALLBACK_NAME_BANK[POICategory.RESTAURANT])
        for offset_index in range(count_per_category):
            name = f"{anchor.text}{names[offset_index % len(names)]}"
            token = stable_token(name, category.value, offset_index)
            if token in seen:
                continue
            seen.add(token)
            angle = (category_index * 71 + offset_index * 43) * math.pi / 180
            distance_km = 0.35 + offset_index * 0.42 + category_index * 0.08
            lat, lng = offset_point(anchor.location.latitude, anchor.location.longitude, distance_km, angle)
            distance_meters = round(haversine_km(anchor.location.latitude, anchor.location.longitude, lat, lng) * 1000)
            pois.append(
                POI(
                    id=f"local-anchor-{token}",
                    name=name,
                    category=category,
                    address=f"{anchor.city}{anchor.text}附近",
                    district=anchor.city or "附近",
                    latitude=lat,
                    longitude=lng,
                    rating=round(4.2 + (offset_index % 3) * 0.15, 1),
                    review_count=120 + offset_index * 80 + category_index * 30,
                    price_per_person=default_price(category) + offset_index * 12,
                    avg_wait_minutes=8 + offset_index * 5,
                    business_hours={"open": "10:00", "close": "22:00"},
                    tags=[category.value, "锚点兜底", "可演示"],
                    ugc_summary="高德 Web 服务未配置或结果不足，使用锚点附近的本地兜底 POI，确保路线仍围绕用户位置生成。",
                    visit_duration_minutes=default_duration(category),
                    source="local",
                    distance_from_anchor_meters=distance_meters,
                )
            )
    return pois


def offset_point(lat: float, lng: float, distance_km: float, angle_rad: float) -> tuple[float, float]:
    dlat = (distance_km * math.cos(angle_rad)) / 111.0
    dlng = (distance_km * math.sin(angle_rad)) / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return lat + dlat, lng + dlng


def stable_token(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def parse_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int(value: Any, default: int | None) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def default_price(category: POICategory) -> float:
    return {
        POICategory.RESTAURANT: 90,
        POICategory.CAFE: 45,
        POICategory.ATTRACTION: 60,
        POICategory.ENTERTAINMENT: 110,
        POICategory.SHOPPING: 80,
        POICategory.ACCOMMODATION: 360,
    }.get(category, 80)


def default_duration(category: POICategory) -> int:
    return {
        POICategory.RESTAURANT: 60,
        POICategory.CAFE: 45,
        POICategory.ATTRACTION: 55,
        POICategory.ENTERTAINMENT: 80,
        POICategory.SHOPPING: 45,
        POICategory.ACCOMMODATION: 90,
    }.get(category, 60)


def estimated_wait(category: POICategory, rating: float, distance_meters: int | None) -> int:
    base = {
        POICategory.RESTAURANT: 18,
        POICategory.CAFE: 10,
        POICategory.ATTRACTION: 8,
        POICategory.ENTERTAINMENT: 12,
        POICategory.SHOPPING: 5,
    }.get(category, 10)
    if rating >= 4.7:
        base += 6
    if distance_meters and distance_meters > 2500:
        base += 4
    return base
