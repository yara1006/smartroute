"""SmartRoute Location/anchor resolution and city detection."""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import HTTPException
from openai import OpenAI

from core.models import (
    GeoPoint,
    MeituanUserContext,
    POI,
    POICategory,
    ParsedIntent,
    Route,
    RouteContext,
    RouteContextPOI,
    RouteIntentResult,
    RouteStop,
    UserProfile,
)
from core.rag.vector_store import haversine_km, transit_minutes
from core.services.amap_client import (
    AMapAnchor,
    AMapClient,
    AMapRouteSegment,
    fallback_pois_around_anchor,
    normalize_city_hint,
    resolve_known_anchor,
)
from schemas import (
    AdjustmentIntent,
    AgentTraceStep,
    CandidateView,
    ChangedStop,
    FollowUp,
    FollowUpOption,
    ImportedProfileView,
    MetricDeltas,
    ProfileInfluence,
    RouteCompleteness,
    RouteInsight,
    RouteMetrics,
    RouteView,
    SearchAnchorView,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
POI_PATH = DATA_DIR / "pois.json"
PROFILE_IMPORTS_PATH = DATA_DIR / "profile_imports.json"
load_dotenv(BASE_DIR / ".env")

def extract_anchor_text(query: str, route_context: RouteContext | None = None) -> str | None:
    """Extract the location/landmark anchor text from the user query or route context."""
    if route_context and route_context.anchor_text:
        return route_context.anchor_text.strip()
    text = query.strip()
    known_names = [
        "深圳万象天地",
        "万象天地",
        "深圳大学",
        "深大",
        "金地威新中心",
        "gaga",
        "科技园",
        "深圳湾",
        "广州永庆坊",
        "永庆坊",
        "外滩",
        "南京东路",
        "陆家嘴",
        "静安寺",
    ]
    for name in known_names:
        if name in text:
            return "万象天地" if name == "深圳万象天地" else name
    for marker in ["附近", "周边"]:
        if marker in text:
            prefix = text.split(marker, 1)[0]
            candidate = clean_anchor_candidate(prefix[-18:])
            if len(candidate) >= 2:
                return candidate
    for marker in ["，", ",", "。", "帮我", "给我", "规划", "安排", "路线"]:
        if marker in text:
            candidate = clean_anchor_candidate(text.split(marker, 1)[0])
            if is_likely_place_anchor(candidate):
                return candidate
    if "从" in text and "出发" in text:
        candidate = clean_anchor_candidate(text.split("从", 1)[1].split("出发", 1)[0])
        if len(candidate) >= 2:
            return candidate[:24]
    return None


def clean_anchor_candidate(value: str) -> str:
    text = value.strip("，。,. 　")
    prefixes = ["我要去", "我想去", "想去", "要去", "我去", "去", "到", "在", "我要", "我想", "想", "要"]
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if text.startswith(prefix) and len(text) > len(prefix) + 1:
                text = text[len(prefix):].strip("，。,. 　")
                changed = True
    return text[:24]


def is_likely_place_anchor(value: str) -> bool:
    text = value.strip()
    if not (2 <= len(text) <= 24):
        return False
    if any(word in text for word in ["什么", "怎么", "多少", "附近", "周边", "今天", "下午", "晚上", "小时"]):
        return False
    suffixes = [
        "天地",
        "中心",
        "广场",
        "商场",
        "公园",
        "大学",
        "学院",
        "书城",
        "博物馆",
        "美术馆",
        "艺术馆",
        "景区",
        "古镇",
        "步行街",
        "购物中心",
        "城",
        "坊",
        "店",
    ]
    return any(text.endswith(suffix) for suffix in suffixes)


def city_hint_from(query: str, intent: ParsedIntent, route_context: RouteContext | None = None) -> str:
    """Infer the city name from the query, parsed intent, or route context."""
    if route_context and route_context.city_hint:
        return normalize_city_hint(route_context.city_hint) or route_context.city_hint
    if any(word in query for word in ["深圳", "深大", "深圳大学", "科技园", "南山"]):
        return "深圳"
    if any(word in query for word in ["上海", "外滩", "陆家嘴", "南京东路", "静安寺", "豫园"]):
        return "上海"
    if any(word in query for word in ["北京", "三里屯", "朝阳", "国贸"]):
        return "北京"
    if any(word in query for word in ["广州", "天河", "珠江新城", "永庆坊", "荔湾", "西关"]):
        return "广州"
    if intent.city and intent.parser_source == "llm":
        return intent.city
    return ""


def requires_live_location_data(query: str, intent: ParsedIntent, route_context: RouteContext | None = None) -> bool:
    """Return True if the request needs real AMap data (non-default city, explicit anchor, or selected POIs)."""
    if route_context and (
        route_context.city_hint
        or route_context.anchor_text
        or route_context.anchor_location
        or route_context.selected_pois
    ):
        return True
    if extract_anchor_text(query, route_context):
        return True
    city_hint = normalize_city_hint(city_hint_from(query, intent, route_context))
    return bool(city_hint and city_hint != "上海")


def context_poi_to_poi(
    item: RouteContextPOI,
    amap_client: AMapClient,
    city_hint: str,
) -> POI | None:
    latitude = item.latitude
    longitude = item.longitude
    if (latitude is None or longitude is None) and amap_client.enabled:
        anchor = amap_client.resolve_anchor(item.address or item.name, city_hint=city_hint)
        if anchor:
            latitude = anchor.location.latitude
            longitude = anchor.location.longitude
    if latitude is None or longitude is None:
        known = resolve_known_anchor(item.name or item.address)
        if known:
            _, point = known
            latitude = point.latitude
            longitude = point.longitude
    if latitude is None or longitude is None:
        return None

    category_text = item.category.value if isinstance(item.category, POICategory) else str(item.category)
    category_aliases = {"咖啡": "咖啡/茶饮", "茶饮": "咖啡/茶饮", "美食": "餐饮", "展览": "景点"}
    category = POICategory(category_aliases.get(category_text, category_text))
    return POI(
        id=item.id or f"context-{abs(hash((item.name, latitude, longitude))) % 1000000}",
        name=item.name,
        category=category,
        address=item.address or f"{city_hint}{item.name}附近",
        district=item.district or city_hint,
        latitude=latitude,
        longitude=longitude,
        rating=item.rating,
        review_count=item.review_count,
        price_per_person=item.price_per_person,
        avg_wait_minutes=item.avg_wait_minutes,
        business_hours=item.business_hours,
        tags=item.tags or [category.value, "用户已选"],
        ugc_summary=item.ugc_summary or "来自入口上下文的用户已选 POI，路线生成时会优先保留。",
        visit_duration_minutes=item.visit_duration_minutes,
        source=item.source,
        external_id=item.external_id,
        distance_from_anchor_meters=None,
    )


def resolve_route_anchor(
    query: str,
    intent: ParsedIntent,
    route_context: RouteContext | None,
    selected_pois: list[POI],
    amap_client: AMapClient,
) -> AMapAnchor | None:
    """Resolve a geographic anchor for the route — from context, AMap, or first selected POI."""
    city_hint = city_hint_from(query, intent, route_context)
    if selected_pois and route_context and route_context.source in {"favorites", "favorite"}:
        first = selected_pois[0]
        return AMapAnchor(
            text=first.name,
            city=normalize_city_hint(first.district) or city_hint,
            location=GeoPoint(latitude=first.latitude, longitude=first.longitude),
            source="selected_poi",
        )
    anchor_text = extract_anchor_text(query, route_context)
    anchor_location = route_context.anchor_location if route_context else None
    anchor = amap_client.resolve_anchor(anchor_text, city_hint=city_hint, anchor_location=anchor_location)
    if anchor:
        return anchor
    if selected_pois:
        first = selected_pois[0]
        return AMapAnchor(
            text=first.name,
            city=normalize_city_hint(first.district) or city_hint,
            location=GeoPoint(latitude=first.latitude, longitude=first.longitude),
            source="selected_poi",
        )
    return None


def unique_categories(categories: list[POICategory]) -> list[POICategory]:
    ordered: list[POICategory] = []
    for category in [
        *categories,
        POICategory.RESTAURANT,
        POICategory.CAFE,
        POICategory.ATTRACTION,
        POICategory.ENTERTAINMENT,
        POICategory.SHOPPING,
    ]:
        if category not in ordered:
            ordered.append(category)
    return ordered[:6]


def categories_for_live_route(query: str, intent: ParsedIntent, base_categories: list[POICategory]) -> list[POICategory]:
    text = f"{query} {intent.extracted_preferences.get('raw_query', '')}"
    ordered: list[POICategory] = []

    def add(category: POICategory) -> None:
        if category not in ordered:
            ordered.append(category)

    if any(word in text for word in ["文化", "展", "展览", "馆", "博物", "美术", "艺术", "景点"]):
        add(POICategory.ATTRACTION)
    if any(word in text for word in ["散步", "步行", "逛", "街区", "公园", "广场", "商圈", "市集", "坊", "天地"]):
        add(POICategory.SHOPPING)
        add(POICategory.ATTRACTION)
    if any(word in text for word in ["喝点东西", "喝东西", "咖啡", "茶", "奶茶", "甜品", "下午茶", "饮品"]):
        add(POICategory.CAFE)
    if any(word in text for word in ["餐饮", "餐厅", "正餐", "吃饭", "午饭", "晚饭", "晚餐", "粤菜", "火锅", "烧烤", "逛吃"]):
        add(POICategory.RESTAURANT)
    if any(word in text for word in ["电影", "演出", "娱乐", "剧场", "密室", "ktv", "KTV"]):
        add(POICategory.ENTERTAINMENT)

    for category in base_categories:
        add(category)
        if len(ordered) >= 4:
            break
    if not ordered:
        ordered = [POICategory.ATTRACTION, POICategory.CAFE, POICategory.SHOPPING]
    return ordered[:4]


def route_role_keywords(query: str, intent: ParsedIntent) -> list[str]:
    text = f"{query} {intent.extracted_preferences.get('raw_query', '')}"
    keywords: list[str] = []
    rules = [
        (["文化", "展", "展览", "馆", "博物", "美术", "艺术"], ["文化", "展览", "博物馆", "艺术馆"]),
        (["散步", "步行", "逛", "街区", "公园", "广场"], ["公园", "步行街", "街区", "广场"]),
        (["喝点东西", "咖啡", "茶", "甜品", "下午茶"], ["咖啡", "茶饮", "下午茶"]),
        (["粤菜", "餐厅", "吃饭", "正餐", "晚餐"], ["餐厅", "特色菜", "本地风味"]),
    ]
    for triggers, terms in rules:
        if any(trigger in text for trigger in triggers):
            keywords.extend(terms)
    return list(dict.fromkeys(keywords))[:10]


def hard_pinned_pois_for_context(route_context: RouteContext | None, selected_pois: list[POI]) -> list[POI]:
    if not route_context:
        return selected_pois
    if route_context.pinned_policy == "fixed_start" and route_context.fixed_start_poi_id:
        return [poi for poi in selected_pois if poi.id == route_context.fixed_start_poi_id][:1]
    if route_context.pinned_policy == "soft":
        return []
    return selected_pois


def fixed_start_pois_from_route(route_context: RouteContext | None, route: Route) -> list[POI]:
    if not route_context or route_context.pinned_policy != "fixed_start" or not route_context.fixed_start_poi_id:
        return []
    fixed_start_id = route_context.fixed_start_poi_id
    return [stop.poi for stop in route.stops if stop.poi.id == fixed_start_id][:1]

