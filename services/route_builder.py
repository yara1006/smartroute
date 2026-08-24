"""SmartRoute Dynamic candidate building and route construction."""
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

# Cross-module imports from anchor_service
from services.anchor_service import (
    categories_for_live_route,
    city_hint_from,
    context_poi_to_poi,
    extract_anchor_text,
    hard_pinned_pois_for_context,
    resolve_route_anchor,
    route_role_keywords,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
POI_PATH = DATA_DIR / "pois.json"
PROFILE_IMPORTS_PATH = DATA_DIR / "profile_imports.json"
load_dotenv(BASE_DIR / ".env")

def build_dynamic_candidates(
    request: PlanRequest,
    intent: ParsedIntent,
    meituan_context: MeituanUserContext,
    amap_client: AMapClient,
    allow_anchor_fallback: bool = True,
) -> tuple[list[tuple[POI, float]], list[POI], AMapAnchor | None, list[str]]:
    route_context = request.route_context
    city_hint = city_hint_from(request.query, intent, route_context)
    selected_pois = [
        poi
        for item in (route_context.selected_pois if route_context else [])
        if (poi := context_poi_to_poi(item, amap_client, city_hint)) is not None
    ]
    anchor = resolve_route_anchor(request.query, intent, route_context, selected_pois, amap_client)
    trace_notes: list[str] = []
    if not anchor:
        return [], selected_pois, None, trace_notes

    resolved_city = anchor.city if anchor.city != "未知城市" else city_hint
    intent.city = resolved_city or intent.city
    intent.constraints.city = resolved_city
    if anchor.city and anchor.city not in intent.constraints.preferred_districts:
        if not intent.constraints.preferred_districts:
            intent.constraints.preferred_districts = [anchor.city]
    intent.extracted_preferences["anchor_text"] = anchor.text
    intent.extracted_preferences["anchor_source"] = anchor.source

    radius = 1500 if meituan_context.walk_preference == "少走路" else 3000
    categories = categories_for_live_route(request.query, intent, intent.constraints.preferred_categories)
    query_keywords = [
        *route_role_keywords(request.query, intent),
        anchor.text,
        *meituan_context.search_preferences[:3],
    ]
    amap_pois = amap_client.search_pois(anchor, categories, keywords=query_keywords, radius_meters=radius)
    if amap_pois:
        trace_notes.append(f"高德 POI：围绕 {anchor.text} {radius}m 按行程角色召回 {len(amap_pois)} 个真实候选。")
    else:
        amap_error_text = "；".join(amap_client.recent_errors())
        trace_notes.append(
            f"高德 POI：{'未配置 Web 服务 Key' if not amap_client.enabled else '召回不足或调用失败'}。"
            + (f" 最近错误：{amap_error_text}" if amap_error_text else "")
        )
        if allow_anchor_fallback:
            trace_notes.append(f"离线兜底：使用 {anchor.text} 附近锚点 POI，不进入上海本地 RAG。")
            amap_pois = fallback_pois_around_anchor(anchor, categories)
        else:
            trace_notes.append("真实地点模式：已禁止使用本地 RAG，避免跨城生成错误路线。")
            amap_pois = []

    hard_pinned_pois = hard_pinned_pois_for_context(route_context, selected_pois)
    pinned_ids = {poi.id for poi in selected_pois}
    candidates: list[tuple[POI, float]] = [(poi, 3.0) for poi in selected_pois]
    if route_context and route_context.pinned_policy == "soft" and selected_pois:
        trace_notes.append("搜索页软选择：勾选 POI 仅作为高权重候选，若破坏路线结构会自动舍弃。")
    for poi in amap_pois:
        if poi.id in pinned_ids:
            continue
        distance_factor = 0.0
        if poi.distance_from_anchor_meters is not None:
            distance_factor = max(0, 0.28 - poi.distance_from_anchor_meters / 12000)
        source_boost = 0.35 if poi.source == "amap" else 0.08
        score = 0.82 + poi.rating / 5 + distance_factor + source_boost
        candidates.append((poi, round(score, 4)))
    return candidates, hard_pinned_pois, anchor, trace_notes


def enrich_route_with_amap_segments(route: Route, amap_client: AMapClient, transport_mode: str) -> Route:
    if len(route.stops) < 2:
        return route
    segments: list[dict[str, Any]] = []
    full_polyline: list[list[float]] = []
    total_transit = 0
    used_amap = False

    for index, stop in enumerate(route.stops[:-1]):
        next_stop = route.stops[index + 1]
        segment = None
        if amap_client.enabled:
            try:
                segment = amap_client.route_segment(
                    stop.poi,
                    next_stop.poi,
                    transport_mode,
                    city=normalize_city_hint(stop.poi.district) or normalize_city_hint(next_stop.poi.district),
                )
            except TypeError:
                segment = amap_client.route_segment(stop.poi, next_stop.poi, transport_mode)
        if segment:
            used_amap = True
            minutes_value = segment.duration_minutes
            polyline = segment.polyline
            distance_km = segment.distance_meters / 1000
            method = {"driving": "打车/驾车", "transit": "公交/地铁", "walking": "步行"}.get(segment.mode, "移动")
            stop.transit_to_next = f"高德{method}约 {minutes_value} 分钟，距离约 {distance_km:.1f} km"
            stop.transit_minutes = minutes_value
            stop.transit_polyline = polyline
            segments.append(
                {
                    "from_order": stop.order,
                    "to_order": next_stop.order,
                    "from_poi_id": stop.poi.id,
                    "to_poi_id": next_stop.poi.id,
                    "mode": segment.mode,
                    "mode_label": method,
                    "strategy": transport_mode,
                    "distance_meters": segment.distance_meters,
                    "duration_minutes": minutes_value,
                    "source": segment.source,
                    "polyline": polyline,
                }
            )
        else:
            polyline = [[stop.poi.longitude, stop.poi.latitude], [next_stop.poi.longitude, next_stop.poi.latitude]]
            minutes_value = stop.transit_minutes or transit_minutes(
                stop.poi.latitude,
                stop.poi.longitude,
                next_stop.poi.latitude,
                next_stop.poi.longitude,
                transport_mode,
            )
            stop.transit_minutes = minutes_value
            stop.transit_polyline = polyline
            segments.append(
                {
                    "from_order": stop.order,
                    "to_order": next_stop.order,
                    "from_poi_id": stop.poi.id,
                    "to_poi_id": next_stop.poi.id,
                    "mode": "fallback",
                    "mode_label": transport_mode or "本地估算",
                    "strategy": transport_mode,
                    "distance_meters": round(haversine_km(stop.poi.latitude, stop.poi.longitude, next_stop.poi.latitude, next_stop.poi.longitude) * 1000),
                    "duration_minutes": minutes_value,
                    "source": "local_estimate",
                    "fallback_reason": "未配置高德 Web 服务 Key或该策略路径规划失败",
                    "polyline": polyline,
                }
            )
        total_transit += minutes_value
        if full_polyline and polyline and full_polyline[-1] == polyline[0]:
            full_polyline.extend(polyline[1:])
        else:
            full_polyline.extend(polyline)

    route.total_transit_minutes = total_transit
    route.map_polyline = full_polyline
    route.transit_segments = segments
    if used_amap:
        route.highlights = list(dict.fromkeys([f"已接入高德{transport_mode}路径耗时与道路 polyline", *route.highlights]))[:4]
    return route


def apply_context_to_candidates(
    candidates: list[tuple[POI, float]],
    context: MeituanUserContext,
) -> list[tuple[POI, float]]:
    favorite_categories = set(context.favorite_categories)
    preferred_districts = set(context.favorite_districts + context.frequent_districts)
    tags = set(context.browsed_tags + context.search_preferences)
    adjusted: list[tuple[POI, float]] = []
    for poi, score in candidates:
        next_score = score
        if poi.category.value in favorite_categories:
            next_score *= 1.16
        if poi.district in preferred_districts:
            next_score *= 1.1
        if tags.intersection(poi.tags):
            next_score *= 1.08
        if poi.avg_wait_minutes <= context.max_wait_preference:
            next_score *= 1.08
        if context.coupon_sensitive and context.common_budget and poi.price_per_person <= context.common_budget:
            next_score *= 1.07
        if context.walk_preference == "少走路" and poi.category in {POICategory.SHOPPING, POICategory.CAFE, POICategory.RESTAURANT}:
            next_score *= 1.05
        adjusted.append((poi, round(next_score, 4)))
    return sorted(adjusted, key=lambda item: item[1], reverse=True)


def build_candidate_view(poi: POI, score: float) -> CandidateView:
    reason_parts = [
        f"{poi.district}",
        f"{poi.category.value}",
        f"评分 {poi.rating:.1f}",
        f"等位约 {poi.avg_wait_minutes} 分钟",
    ]
    if poi.tags:
        reason_parts.append(" / ".join(poi.tags[:2]))
    return CandidateView(poi=poi, score=round(score, 3), reason=" · ".join(reason_parts))


def poi_to_context_poi(poi: POI) -> RouteContextPOI:
    return RouteContextPOI(
        id=poi.id,
        name=poi.name,
        category=poi.category,
        address=poi.address,
        district=poi.district,
        latitude=poi.latitude,
        longitude=poi.longitude,
        rating=poi.rating,
        review_count=poi.review_count,
        price_per_person=poi.price_per_person,
        avg_wait_minutes=poi.avg_wait_minutes,
        business_hours=poi.business_hours,
        tags=poi.tags,
        ugc_summary=poi.ugc_summary,
        visit_duration_minutes=poi.visit_duration_minutes,
        source=poi.source,
        external_id=poi.external_id,
    )


def default_search_selected_pois(candidates: list[tuple[POI, float]], max_count: int = 4) -> list[RouteContextPOI]:
    selected: list[POI] = []
    seen_categories: set[POICategory] = set()
    for poi, _ in candidates:
        if poi.id in {item.id for item in selected}:
            continue
        if poi.category not in seen_categories:
            selected.append(poi)
            seen_categories.add(poi.category)
        if len(selected) >= max_count:
            break
    for poi, _ in candidates:
        if len(selected) >= max(2, min(max_count, len(candidates))):
            break
        if poi.id in {item.id for item in selected}:
            continue
        selected.append(poi)
    return [poi_to_context_poi(poi) for poi in selected[:max_count]]


