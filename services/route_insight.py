"""SmartRoute Route analysis, metrics, follow-up generation."""
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

def route_insight(route: Route, intent: ParsedIntent) -> RouteInsight:
    constraints = intent.constraints
    target_minutes = int(constraints.total_time_hours * 60)
    time_hit = route.total_time_minutes <= target_minutes
    wait_hit = route.total_wait_minutes <= constraints.max_wait_minutes * max(1, len(route.stops))
    budget_left = None
    budget_hit = True
    if constraints.budget_per_person is not None:
        budget_left = round(constraints.budget_per_person - route.total_cost_per_person, 1)
        budget_hit = budget_left >= 0

    district_hit = True
    if constraints.preferred_districts:
        districts = {stop.poi.district for stop in route.stops}
        district_hit = bool(districts.intersection(constraints.preferred_districts))

    categories = {stop.poi.category for stop in route.stops}
    has_meal = bool(categories.intersection({POICategory.RESTAURANT, POICategory.CAFE}))
    has_culture = bool(categories.intersection({POICategory.ATTRACTION, POICategory.ENTERTAINMENT, POICategory.SHOPPING}))
    route_complete = len(route.stops) >= 3

    hit_labels = [
        "总时长命中" if time_hit else "总时长接近上限",
        "预算命中" if budget_hit else "预算略超",
        "低排队命中" if wait_hit else "排队风险偏高",
        "区域命中" if district_hit else "区域已放宽",
        "距离/步行可控" if route.total_transit_minutes <= constraints.max_walk_minutes * max(1, len(route.stops) - 1) else "距离/步行偏高",
        ">=3 POI" if route_complete else "POI 数不足",
        "餐饮+文化/娱乐/散步覆盖" if has_meal and has_culture else "类型覆盖不足",
    ]

    score = 64
    score += 10 if time_hit else -6
    score += 10 if budget_hit else -8
    score += 8 if wait_hit else -6
    score += 6 if district_hit else -3
    score += 8 if route_complete else -12
    score += 6 if has_meal and has_culture else -10
    score += min(len(route.highlights) * 3, 9)
    score -= len(route.warnings) * 4
    confidence_score = max(45, min(96, score))

    average_transit = route.total_transit_minutes / max(1, len(route.stops) - 1)
    if average_transit <= 10:
        walk_intensity = "轻松"
    elif average_transit <= 18:
        walk_intensity = "适中"
    else:
        walk_intensity = "偏高"

    if route.total_wait_minutes <= 20:
        wait_status = "低排队"
    elif route.total_wait_minutes <= 45:
        wait_status = "可接受"
    else:
        wait_status = "需错峰"

    special = intent.extracted_preferences.get("special_requirements", "")
    if "带老人" in special or "少走路" in special or "爸妈" in special:
        crowd_fit = "适合爸妈/老人"
    elif "亲子" in intent.extracted_preferences.get("travel_style", ""):
        crowd_fit = "适合亲子"
    elif "浪漫" in intent.extracted_preferences.get("travel_style", ""):
        crowd_fit = "适合情侣"
    else:
        crowd_fit = "适合朋友/轻约会"

    indoor_count = sum(1 for stop in route.stops if stop.poi.category.value in {"餐饮", "购物", "咖啡/茶饮", "娱乐"})
    weather_fit = "雨天也稳" if indoor_count >= max(2, len(route.stops) - 1) else "晴天更佳"

    explanation = "、".join(route.highlights[:2]) if route.highlights else route.description
    return RouteInsight(
        route_id=route.id,
        confidence_score=confidence_score,
        constraint_hits=hit_labels,
        budget_left=budget_left,
        wait_status=wait_status,
        walk_intensity=walk_intensity,
        crowd_fit=crowd_fit,
        weather_fit=weather_fit,
        explanation=explanation,
        risks=route.warnings,
    )


def build_route_completeness(route: Route | None) -> RouteCompleteness | None:
    if route is None:
        return None
    categories = {stop.poi.category for stop in route.stops}
    has_meal = bool(categories.intersection({POICategory.RESTAURANT, POICategory.CAFE}))
    has_culture = bool(categories.intersection({POICategory.ATTRACTION, POICategory.ENTERTAINMENT, POICategory.SHOPPING}))
    notes = []
    if len(route.stops) < 3:
        notes.append("POI 数不足 3 个")
    if not has_meal:
        notes.append("缺少餐饮或咖啡休息点")
    if not has_culture:
        notes.append("缺少文化/娱乐/散步体验点")
    if not notes:
        notes.append("路线满足 3 个以上 POI 串联，并覆盖餐饮 + 文化/娱乐/散步")
    return RouteCompleteness(
        stop_count=len(route.stops),
        has_meal=has_meal,
        has_culture_or_entertainment=has_culture,
        is_complete=len(route.stops) >= 3 and has_meal and has_culture,
        notes=notes,
    )


def build_constraint_conflicts(route: Route | None, intent: ParsedIntent) -> list[str]:
    if route is None:
        return ["当前约束下没有生成可执行路线"]
    constraints = intent.constraints
    conflicts = list(route.warnings)
    if constraints.budget_per_person and route.total_cost_per_person > constraints.budget_per_person:
        conflicts.append(f"人均 ¥{route.total_cost_per_person:.0f} 超出预算 ¥{constraints.budget_per_person:.0f}")
    wait_limit = constraints.max_wait_minutes * max(1, len(route.stops))
    if route.total_wait_minutes > wait_limit:
        conflicts.append(f"总等待 {route.total_wait_minutes} 分钟高于当前排队容忍度")
    walk_limit = constraints.max_walk_minutes * max(1, len(route.stops) - 1)
    if route.total_transit_minutes > walk_limit:
        conflicts.append(f"路上交通约 {route.total_transit_minutes} 分钟，步行/距离强度偏高")
    completeness = build_route_completeness(route)
    if completeness and not completeness.is_complete:
        conflicts.extend(completeness.notes)
    return list(dict.fromkeys(conflicts))[:5]


def route_metrics(route: Route) -> RouteMetrics:
    return RouteMetrics(
        stop_count=len(route.stops),
        total_time_minutes=route.total_time_minutes,
        total_cost_per_person=round(route.total_cost_per_person, 1),
        total_wait_minutes=route.total_wait_minutes,
        total_transit_minutes=route.total_transit_minutes,
    )


def metric_deltas(before: RouteMetrics, after: RouteMetrics) -> MetricDeltas:
    return MetricDeltas(
        stop_count=after.stop_count - before.stop_count,
        total_time_minutes=after.total_time_minutes - before.total_time_minutes,
        total_cost_per_person=round(after.total_cost_per_person - before.total_cost_per_person, 1),
        total_wait_minutes=after.total_wait_minutes - before.total_wait_minutes,
        total_transit_minutes=after.total_transit_minutes - before.total_transit_minutes,
    )


def build_profile_influence(context: MeituanUserContext, route: Route | None) -> list[ProfileInfluence]:
    stops = route.stops if route else []
    context_tags = set(context.search_preferences + context.browsed_tags)
    preferred_districts = set(context.favorite_districts + context.frequent_districts)

    def names_for(predicate: Any, limit: int = 3) -> list[str]:
        return [stop.poi.name for stop in stops if predicate(stop.poi)][:limit]

    category_matches = names_for(lambda poi: poi.category.value in context.favorite_categories)
    district_matches = names_for(lambda poi: poi.district in preferred_districts)
    tag_matches = names_for(lambda poi: bool(set(poi.tags).intersection(context_tags)))
    wait_matches = names_for(lambda poi: poi.avg_wait_minutes <= context.max_wait_preference)
    budget_matches = names_for(
        lambda poi: context.common_budget is not None and poi.price_per_person <= context.common_budget
    )

    return [
        ProfileInfluence(
            signal="搜索偏好 / 浏览标签",
            source="、".join((context.search_preferences + context.browsed_tags)[:5]),
            effect="召回时提高带有相近标签的 POI 分数，让结果更贴近近期兴趣。",
            matched_pois=tag_matches,
            weight="高",
        ),
        ProfileInfluence(
            signal="收藏偏好类型",
            source="、".join(context.favorite_categories[:4]),
            effect="路线组合优先覆盖这些类型，并保证餐饮 + 文化/娱乐的可执行结构。",
            matched_pois=category_matches,
            weight="高",
        ),
        ProfileInfluence(
            signal="常去商圈 / 收藏地区",
            source="、".join(list(dict.fromkeys(context.favorite_districts + context.frequent_districts))[:4]),
            effect="同等条件下优先选择熟悉商圈，减少跨区移动和决策成本。",
            matched_pois=district_matches,
            weight="中",
        ),
        ProfileInfluence(
            signal="排队容忍度",
            source=f"最多约 {context.max_wait_preference} 分钟",
            effect="降低高等待 POI 的排序权重，并在解释中暴露排队风险。",
            matched_pois=wait_matches,
            weight="高",
        ),
        ProfileInfluence(
            signal="预算 / 优惠敏感度",
            source=(
                f"常用预算 ¥{context.common_budget:.0f}，{'关注优惠' if context.coupon_sensitive else '更关注体验'}"
                if context.common_budget
                else "预算未沉淀"
            ),
            effect="预算友好路线会优先控制人均，高体验路线允许为高评分 POI 留出预算空间。",
            matched_pois=budget_matches,
            weight="中",
        ),
    ]


def build_follow_up(
    route_view: RouteView | None,
    intent: ParsedIntent,
    conflicts: list[str],
    context: MeituanUserContext,
) -> FollowUp:
    if route_view is None:
        return FollowUp(
            question="当前约束比较紧，要不要先放宽区域、预算或排队限制？",
            reason="没有生成完整路线，需要先降低约束冲突。",
            options=[
                FollowUpOption(label="放宽区域", instruction="区域放宽一点", expected_effect="扩大候选 POI 范围"),
                FollowUpOption(label="接受短等位", instruction="可以排队久一点", expected_effect="增加高评分热门店候选"),
                FollowUpOption(label="延长时间", instruction="时间可以延长半小时", expected_effect="给路线留出移动和停留缓冲"),
            ],
        )

    raw_query = intent.extracted_preferences.get("raw_query", "")
    missing_preferences = []
    if intent.constraints.budget_per_person is None and not any(word in raw_query for word in ["预算", "人均", "便宜", "贵"]):
        missing_preferences.append("预算")
    if not any(word in raw_query for word in ["排队", "等位", "不排队"]):
        missing_preferences.append("排队")
    if not any(word in raw_query for word in ["少走路", "打车", "步行"]):
        missing_preferences.append("步行")

    if route_view.insight.confidence_score < 78 or conflicts:
        question = "这条路线还有可优化空间，你更想先优化哪一项？"
        reason = "路线存在约束冲突或置信度不足，适合进入多轮局部调整。"
    elif missing_preferences:
        question = f"我已按{context.profile_mode}偏好规划。还要补充{ '、'.join(missing_preferences) }要求吗？"
        reason = "原始需求没有说清全部约束，追问能减少后续返工。"
    else:
        question = "要不要继续把路线调得更贴近你的使用习惯？"
        reason = "路线已可执行，但仍可以通过反馈做个性化微调。"

    options: list[FollowUpOption] = []
    used: set[str] = set()

    def add_option(label: str, instruction: str, expected_effect: str) -> None:
        if instruction in used:
            return
        used.add(instruction)
        options.append(FollowUpOption(label=label, instruction=instruction, expected_effect=expected_effect))

    add_option("少排队", "不要排队", "优先替换等位最高的站点")
    add_option("便宜点", "便宜点", "优先替换人均最高的餐饮/咖啡站点")
    add_option("少走路", "少走路一点", "优先重排或替换移动距离最高的站点")
    if context.profile_mode == "文艺体验型":
        add_option("加展览", "加展览", "加入文化/展览类 POI，保持路线体验感")
    elif context.profile_mode == "带爸妈轻松型":
        add_option("加休息点", "加咖啡休息", "加入可休息的咖啡/茶饮点，降低疲劳")
    else:
        add_option("更稳妥", "不要排队，便宜点", "优先控制等待和预算，减少踩雷风险")

    return FollowUp(question=question, options=options, reason=reason)


def build_follow_up_question(
    route_view: RouteView | None,
    intent: ParsedIntent,
    conflicts: list[str],
    context: MeituanUserContext,
) -> str | None:
    return build_follow_up(route_view, intent, conflicts, context).question

