"""SmartRoute Route adjustment and modification logic."""
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

def build_changed_stops(before: Route, after: Route, changed_orders: list[int]) -> list[ChangedStop]:
    changed_order_set = set(changed_orders)
    before_ids = [stop.poi.id for stop in before.stops]
    after_ids = [stop.poi.id for stop in after.stops]
    before_id_set = set(before_ids)
    after_id_set = set(after_ids)
    changes: list[ChangedStop] = []
    for index in range(max(len(before.stops), len(after.stops))):
        before_stop = before.stops[index] if index < len(before.stops) else None
        after_stop = after.stops[index] if index < len(after.stops) else None
        order = index + 1
        if before_stop and after_stop and before_stop.poi.id == after_stop.poi.id and order not in changed_order_set:
            continue
        if before_stop is None and after_stop is not None:
            action = "added"
            explanation = f"新增 {after_stop.poi.category.value} 站点，补足当前调整诉求。"
        elif before_stop is not None and after_stop is None:
            action = "removed"
            explanation = "移除该站点以保证路线仍可执行。"
        elif before_stop and after_stop and before_stop.poi.id in after_id_set and after_stop.poi.id in before_id_set:
            action = "reordered"
            explanation = "调整站点顺序，减少移动或让时间线更顺。"
        else:
            action = "replaced"
            explanation = "替换站点以优化当前指令对应的指标。"
        changes.append(
            ChangedStop(
                order=order,
                action=action,
                before_poi=before_stop.poi.name if before_stop else None,
                after_poi=after_stop.poi.name if after_stop else None,
                explanation=explanation,
            )
        )
    return changes


def objective_improved(kind: str, deltas: MetricDeltas) -> bool:
    if kind == "cheaper":
        return deltas.total_cost_per_person < 0
    if kind == "wait":
        return deltas.total_wait_minutes < 0
    if kind == "walk":
        return deltas.total_transit_minutes < 0
    if kind == "add":
        return deltas.stop_count > 0 or deltas.total_time_minutes <= 30
    if kind == "focus":
        return True
    return False


def adjustment_status_for(
    kind: str,
    before: Route,
    after: Route,
    changed_stops: list[ChangedStop],
    deltas: MetricDeltas,
    candidate: POI | None,
) -> Literal["applied", "partial", "not_applied"]:
    before_signature = [stop.poi.id for stop in before.stops]
    after_signature = [stop.poi.id for stop in after.stops]
    route_changed = before_signature != after_signature or len(before.stops) != len(after.stops)
    if not route_changed or not changed_stops:
        return "not_applied"
    if kind in {"cheaper", "wait", "walk"} and not objective_improved(kind, deltas):
        return "partial"
    if kind in {"add", "focus"} and candidate is None:
        return "partial"
    return "applied"


def adjustment_intent_satisfied(intent: AdjustmentIntent, route: Route) -> bool:
    if intent.kind == "avoid_stop" and intent.target_text:
        target = intent.target_text.lower()
        return all(target not in stop.poi.name.lower() for stop in route.stops)
    if intent.kind == "avoid_category" and intent.categories:
        return all(stop.poi.category not in intent.categories for stop in route.stops)
    if intent.kind == "reduce_category" and intent.categories:
        count = sum(1 for stop in route.stops if stop.poi.category in intent.categories)
        return count <= (intent.max_count if intent.max_count is not None else 1)
    return True


def suggested_relaxations_for(
    kind: str,
    status: Literal["applied", "partial", "not_applied"],
    conflicts: list[str],
) -> list[str]:
    if status == "applied":
        return []
    suggestions = []
    if kind == "cheaper":
        suggestions.append("可把人均预算上限放宽 30-50 元，或允许替换成咖啡/小吃类轻餐。")
    elif kind == "wait":
        suggestions.append("可接受 15-20 分钟等位，或把热门餐饮改成错峰时段。")
    elif kind == "walk":
        suggestions.append("可允许短途打车，或把活动范围收窄到同一商圈。")
    elif kind == "add":
        suggestions.append("可延长 30 分钟，或允许替换掉当前匹配度最低的一站。")
    elif kind == "focus":
        suggestions.append("可放宽活动类型，或把范围扩大到附近 3-5 公里以补足文化/娱乐/购物点。")
    if any("预算" in conflict for conflict in conflicts):
        suggestions.append("当前预算约束较紧，建议优先放宽预算或减少正餐数量。")
    if any("排队" in conflict or "等待" in conflict for conflict in conflicts):
        suggestions.append("当前排队约束较紧，建议选择低峰时间或低等待替代店。")
    if any("步行" in conflict or "交通" in conflict for conflict in conflicts):
        suggestions.append("当前移动强度偏高，建议放宽交通方式为短途打车。")
    return list(dict.fromkeys(suggestions))[:4]


def detect_adjustment_kind(instruction: str) -> tuple[str, set[POICategory] | None]:
    text = instruction.strip()
    if any(word in text for word in ["太多餐厅", "太多吃的", "不要这么多餐厅", "别这么多餐厅", "全是餐厅", "都是餐厅", "餐厅太多", "少点餐厅", "少一点餐厅"]):
        return "focus", {POICategory.ATTRACTION, POICategory.ENTERTAINMENT, POICategory.SHOPPING, POICategory.CAFE}
    if any(word in text for word in ["不要这么多咖啡", "别这么多咖啡", "全是咖啡", "都是咖啡", "咖啡太多", "太多咖啡", "少点咖啡", "少一点咖啡", "不要全是咖啡"]):
        return "focus", {POICategory.ATTRACTION, POICategory.ENTERTAINMENT, POICategory.SHOPPING, POICategory.RESTAURANT}
    if any(word in text for word in ["换个重点", "重点", "不想都是", "太多同类", "更丰富", "换一类"]):
        return "focus", {POICategory.ATTRACTION, POICategory.ENTERTAINMENT, POICategory.SHOPPING, POICategory.RESTAURANT}
    if any(word in text for word in ["少走", "近一点", "距离", "别太远", "打车少"]):
        return "walk", None
    if any(word in text for word in ["便宜", "省钱", "预算", "贵"]):
        return "cheaper", None
    if any(word in text for word in ["不排队", "少排队", "等待", "等位", "排队"]):
        return "wait", None
    if any(word in text for word in ["晚餐", "吃饭", "餐厅", "正餐", "粤菜", "菜馆", "酒楼", "饭店"]):
        return "add", {POICategory.RESTAURANT}
    if any(word in text for word in ["咖啡", "下午茶", "甜品", "休息"]):
        return "add", {POICategory.CAFE}
    if any(word in text for word in ["展览", "展", "景点", "文化", "美术馆"]):
        return "add", {POICategory.ATTRACTION, POICategory.ENTERTAINMENT}
    if any(word in text for word in ["文艺", "拍照", "设计感"]):
        return "add", {POICategory.ATTRACTION, POICategory.ENTERTAINMENT, POICategory.CAFE}
    return "wait", None


CATEGORY_ALIASES: dict[POICategory, list[str]] = {
    POICategory.RESTAURANT: ["吃饭", "晚饭", "午饭", "正餐", "餐厅", "餐饮", "吃的", "美食", "火锅", "小吃"],
    POICategory.CAFE: ["咖啡", "咖啡馆", "咖啡店", "喝咖啡", "下午茶", "奶茶", "甜品", "茶饮"],
    POICategory.ATTRACTION: ["展览", "看展", "景点", "公园", "博物馆", "美术馆", "文化"],
    POICategory.ENTERTAINMENT: ["娱乐", "电影", "酒吧", "演出", "live", "ktv", "密室"],
    POICategory.SHOPPING: ["购物", "逛街", "商场", "市集", "买东西"],
}


NEGATIVE_ADJUSTMENT_TERMS = ["不想", "不要", "别", "不去", "去掉", "删掉", "移除", "换掉", "避开", "不喝", "不吃"]
REDUCE_ADJUSTMENT_TERMS = [
    "少安排",
    "少一点",
    "少点",
    "不要两家",
    "不要多个",
    "不要这么多",
    "别这么多",
    "别太多",
    "太多",
    "都是",
    "全是",
    "减少",
]


def mentioned_categories(instruction: str) -> set[POICategory]:
    text = instruction.lower()
    categories: set[POICategory] = set()
    for category, aliases in CATEGORY_ALIASES.items():
        if any(alias.lower() in text for alias in aliases):
            categories.add(category)
    return categories


def has_negative_adjustment(instruction: str) -> bool:
    text = instruction.lower()
    return any(term in text for term in NEGATIVE_ADJUSTMENT_TERMS)


def has_reduce_adjustment(instruction: str) -> bool:
    text = instruction.lower()
    return any(term in text for term in REDUCE_ADJUSTMENT_TERMS)


def choose_category_target(route: Route, categories: set[POICategory]) -> int | None:
    matches = [
        (index, stop.wait_minutes, stop.poi.price_per_person)
        for index, stop in enumerate(route.stops)
        if stop.poi.category in categories
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: (item[1], item[2]))[0]


def mentioned_stop_index(route: Route, instruction: str) -> int | None:
    text = instruction.strip().lower()
    if not any(word in text for word in ["不想去", "不要去", "别去", "不去", "去掉", "删掉", "移除", "换掉", "避开"]):
        return None

    phrases = [
        "我不想去",
        "不想去",
        "不要去",
        "别去",
        "不去",
        "去掉",
        "删掉",
        "移除",
        "换掉",
        "避开",
        "这个",
        "这家",
        "那家",
        "那个",
    ]
    keyword = text
    for phrase in phrases:
        keyword = keyword.replace(phrase, " ")
    keyword = re.sub(r"[，。,.!！?？、；;：:\s]+", " ", keyword).strip()
    tokens = [token for token in keyword.split(" ") if len(token) >= 2]

    best_index: int | None = None
    best_score = 0
    for index, stop in enumerate(route.stops):
        searchable = " ".join(
            [
                stop.poi.name,
                stop.poi.address,
                stop.poi.district,
                stop.poi.category.value,
                *stop.poi.tags,
            ]
        ).lower()
        score = 0
        for token in tokens:
            if token in searchable:
                score += len(token)
        if score > best_score:
            best_score = score
            best_index = index

    return best_index if best_score > 0 else None


def parse_adjustment_intent(
    instruction: str,
    route: Route,
    llm_adjustment: tuple[str, set[POICategory] | None, str, str] | None = None,
) -> AdjustmentIntent:
    mentioned_index = mentioned_stop_index(route, instruction)
    if mentioned_index is not None:
        stop = route.stops[mentioned_index]
        return AdjustmentIntent(
            kind="avoid_stop",
            categories={stop.poi.category},
            target_index=mentioned_index,
            target_text=stop.poi.name,
            source="rules",
            reason=f"命中用户不想去的站点：{stop.poi.name}",
        )

    categories = mentioned_categories(instruction)
    if categories and (has_negative_adjustment(instruction) or has_reduce_adjustment(instruction)):
        target_index = choose_category_target(route, categories)
        reduce_only = has_reduce_adjustment(instruction)
        return AdjustmentIntent(
            kind="reduce_category" if reduce_only else "avoid_category",
            categories=categories,
            target_index=target_index,
            target_text="、".join(category.value for category in categories),
            max_count=1 if reduce_only else 0,
            source="rules",
            reason=f"命中用户不想要的类型：{'、'.join(category.value for category in categories)}",
        )

    if llm_adjustment:
        kind, categories, source, reason = llm_adjustment
        return AdjustmentIntent(kind=kind, categories=categories, source=source, reason=reason)

    kind, categories = detect_adjustment_kind(instruction)
    return AdjustmentIntent(kind=kind, categories=categories)


def distance_around(route: Route, index: int, poi: POI) -> float:
    distance = 0.0
    if index > 0:
        prev = route.stops[index - 1].poi
        distance += haversine_km(prev.latitude, prev.longitude, poi.latitude, poi.longitude)
    if index + 1 < len(route.stops):
        nxt = route.stops[index + 1].poi
        distance += haversine_km(poi.latitude, poi.longitude, nxt.latitude, nxt.longitude)
    return distance


def find_adjustment_candidate(
    route: Route,
    candidates: list[tuple[POI, float]],
    kind: str,
    target_index: int,
    categories: set[POICategory] | None = None,
) -> POI | None:
    current_ids = {stop.poi.id for stop in route.stops}
    target_stop = route.stops[target_index]
    category_filter = categories or {target_stop.poi.category}
    if kind in {"avoid_stop", "avoid_category", "reduce_category"}:
        avoid_categories = categories or {target_stop.poi.category}
        options = [poi for poi, _ in candidates if poi.id not in current_ids and poi.category not in avoid_categories]
    else:
        options = [poi for poi, _ in candidates if poi.id not in current_ids and poi.category in category_filter]
    if not options:
        return None
    if kind == "focus":
        return sorted(
            options,
            key=lambda poi: (
                poi.category in {POICategory.RESTAURANT, POICategory.CAFE},
                -poi.rating,
                poi.avg_wait_minutes,
                poi.price_per_person,
            ),
        )[0]
    if kind == "cheaper":
        cheaper = [poi for poi in options if poi.price_per_person < target_stop.poi.price_per_person]
        if not cheaper:
            return None
        return sorted(cheaper, key=lambda poi: (poi.price_per_person, poi.avg_wait_minutes, -poi.rating))[0]
    if kind == "wait":
        lower_wait = [poi for poi in options if poi.avg_wait_minutes < target_stop.wait_minutes]
        if not lower_wait:
            return None
        return sorted(lower_wait, key=lambda poi: (poi.avg_wait_minutes, poi.price_per_person, -poi.rating))[0]
    if kind == "walk":
        old_distance = distance_around(route, target_index, target_stop.poi)
        closer = [poi for poi in options if distance_around(route, target_index, poi) < old_distance]
        if not closer:
            return None
        return sorted(closer, key=lambda poi: (distance_around(route, target_index, poi), poi.avg_wait_minutes, -poi.rating))[0]
    if kind in {"avoid_stop", "avoid_category", "reduce_category"}:
        def replacement_role_rank(poi: POI) -> int:
            if POICategory.CAFE in avoid_categories and poi.category == POICategory.RESTAURANT:
                return 0
            if poi.category in {POICategory.ATTRACTION, POICategory.SHOPPING, POICategory.ENTERTAINMENT}:
                return 1
            return 2

        return sorted(
            options,
            key=lambda poi: (
                replacement_role_rank(poi),
                distance_around(route, target_index, poi),
                poi.avg_wait_minutes,
                -poi.rating,
                poi.price_per_person,
            ),
        )[0]
    return sorted(options, key=lambda poi: (poi.avg_wait_minutes, -poi.rating, poi.price_per_person))[0]


def is_core_route_stop(stop: RouteStop, route: Route) -> bool:
    anchor_words = ["永庆坊", "大学", "公园", "博物馆", "美术馆", "艺术馆", "景区", "古镇", "步行街"]
    if stop.poi.category in {POICategory.ATTRACTION, POICategory.ENTERTAINMENT}:
        return True
    if any(word in stop.poi.name for word in anchor_words):
        return True
    return len(route.stops) <= 3 and stop.order == 2 and stop.poi.category == POICategory.SHOPPING


def choose_add_target(route: Route, categories: set[POICategory] | None) -> int:
    desired = categories or set()
    if POICategory.RESTAURANT in desired:
        replaceable_priority = [
            POICategory.SHOPPING,
            POICategory.CAFE,
            POICategory.ENTERTAINMENT,
        ]
    elif POICategory.CAFE in desired:
        replaceable_priority = [
            POICategory.SHOPPING,
            POICategory.RESTAURANT,
            POICategory.ENTERTAINMENT,
        ]
    else:
        replaceable_priority = [
            POICategory.SHOPPING,
            POICategory.CAFE,
            POICategory.RESTAURANT,
        ]

    for category in replaceable_priority:
        matches = [
            (index, stop.poi.rating, stop.wait_minutes)
            for index, stop in enumerate(route.stops)
            if stop.poi.category == category and not is_core_route_stop(stop, route)
        ]
        if matches:
            return min(matches, key=lambda item: (item[1], -item[2]))[0]

    non_core = [
        (index, stop.poi.rating, stop.wait_minutes)
        for index, stop in enumerate(route.stops)
        if not is_core_route_stop(stop, route)
    ]
    if non_core:
        return min(non_core, key=lambda item: (item[1], -item[2]))[0]
    return len(route.stops) - 1


def choose_adjustment_target(route: Route, kind: str) -> int:
    if kind == "focus":
        seen_categories: set[POICategory] = set()
        for index, stop in enumerate(route.stops):
            if stop.poi.category == POICategory.CAFE and index > 0:
                return index
            if stop.poi.category in seen_categories and stop.poi.category in {POICategory.CAFE, POICategory.RESTAURANT}:
                return index
            seen_categories.add(stop.poi.category)
        foodish = [
            (index, stop.poi.rating)
            for index, stop in enumerate(route.stops)
            if stop.poi.category in {POICategory.CAFE, POICategory.RESTAURANT}
        ]
        if foodish:
            return min(foodish, key=lambda item: item[1])[0]
        return len(route.stops) - 1
    if kind == "cheaper":
        priced = [
            (index, stop.poi.price_per_person)
            for index, stop in enumerate(route.stops)
            if stop.poi.category in {POICategory.RESTAURANT, POICategory.CAFE}
        ]
        return max(priced or list(enumerate([stop.poi.price_per_person for stop in route.stops])), key=lambda item: item[1])[0]
    if kind == "wait":
        return max(range(len(route.stops)), key=lambda index: route.stops[index].wait_minutes)
    if kind == "walk":
        transit_pairs = [(index, stop.transit_minutes or 0) for index, stop in enumerate(route.stops[:-1])]
        if not transit_pairs:
            return min(1, len(route.stops) - 1)
        max_index = max(transit_pairs, key=lambda item: item[1])[0]
        return min(max_index + 1, len(route.stops) - 1)
    return len(route.stops) - 1


def add_intent_satisfied(categories: set[POICategory] | None, route: Route) -> bool:
    if not categories:
        return True
    return any(stop.poi.category in categories for stop in route.stops)


def adjustment_search_terms(instruction: str, categories: set[POICategory] | None) -> list[str]:
    text = instruction.strip()
    terms: list[str] = []
    if categories and POICategory.RESTAURANT in categories:
        if "粤菜" in text:
            terms.extend(["粤菜", "广东菜", "酒楼", "地道粤菜", "餐厅"])
        elif any(word in text for word in ["火锅", "烧烤", "小吃"]):
            terms.extend([word for word in ["火锅", "烧烤", "小吃", "餐厅"] if word in text or word == "餐厅"])
        else:
            terms.extend(["餐厅", "本地菜", "特色菜"])
    if categories and POICategory.CAFE in categories:
        terms.extend(["咖啡", "茶饮", "下午茶", "甜品"])
    if categories and POICategory.ATTRACTION in categories:
        terms.extend(["文化", "展览", "博物馆", "艺术馆"])
    if categories and POICategory.SHOPPING in categories:
        terms.extend(["街区", "步行街", "商场", "散步"])
    if text:
        terms.append(text)
    return list(dict.fromkeys(terms))[:8]


def adjustment_summary(
    kind: str,
    instruction: str,
    changed_name: str | None,
    status: Literal["applied", "partial", "not_applied"] = "applied",
    deltas: MetricDeltas | None = None,
) -> str:
    if status == "not_applied":
        return f"暂时没有找到能满足“{instruction}”且不破坏路线完整性的替换项，已保留原路线。"
    if status == "partial":
        return f"已尝试按“{instruction}”局部调整，但核心指标改善有限，建议继续放宽约束。"
    target = changed_name or "当前路线"
    if kind == "walk":
        transit_delta = abs(deltas.total_transit_minutes) if deltas else 0
        return f"已根据“{instruction}”优化站点顺序/距离，路上移动减少约 {transit_delta} 分钟。"
    if kind == "cheaper":
        cost_delta = abs(deltas.total_cost_per_person) if deltas else 0
        return f"已根据“{instruction}”将高预算站点替换为 {target}，人均降低约 ¥{cost_delta:.0f}。"
    if kind == "wait":
        wait_delta = abs(deltas.total_wait_minutes) if deltas else 0
        return f"已根据“{instruction}”将高等待站点替换为 {target}，总等待减少约 {wait_delta} 分钟。"
    if kind == "avoid_stop":
        return f"已根据“{instruction}”避开指定站点，并替换为 {target}，保持路线仍可执行。"
    if kind == "avoid_category":
        return f"已根据“{instruction}”避开指定类型，并替换为 {target}，保持路线仍可执行。"
    if kind == "reduce_category":
        return f"已根据“{instruction}”减少指定类型站点，并替换为 {target}，保持路线仍可执行。"
    if kind == "focus":
        return f"已根据“{instruction}”把重复/弱重点站替换为 {target}，让路线更像真实的一次出行。"
    return f"已根据“{instruction}”加入或替换为 {target}，保持路线仍可执行。"

