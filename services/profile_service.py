"""SmartRoute User profile management and context building."""
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

def ensure_data() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not POI_PATH.exists():
        pois = generate_mock_pois(500)
        POI_PATH.write_text(json.dumps(pois, ensure_ascii=False, indent=2), encoding="utf-8")
        (DATA_DIR / "ugc_reviews.json").write_text(
            json.dumps(generate_reviews(pois), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


PROFILE_CONTEXTS: dict[str, dict[str, Any]] = {
    "低排队务实型": {
        "search_preferences": ["不排队", "性价比", "优惠套餐", "本地人推荐"],
        "favorite_categories": ["餐饮", "咖啡/茶饮", "景点"],
        "favorite_districts": ["黄浦区", "静安区"],
        "browsed_tags": ["不踩雷", "性价比高", "基本不用等位", "适合朋友"],
        "common_budget": 150.0,
        "frequent_districts": ["黄浦区", "静安区"],
        "max_wait_preference": 12,
        "walk_preference": "适中",
        "coupon_sensitive": True,
        "summary": "近期常搜低排队、优惠和本地人推荐，路线会优先控制等待与预算。",
    },
    "文艺体验型": {
        "search_preferences": ["咖啡", "展览", "拍照", "有设计感"],
        "favorite_categories": ["咖啡/茶饮", "景点", "购物", "餐饮"],
        "favorite_districts": ["黄浦区", "徐汇区", "静安区"],
        "browsed_tags": ["安静", "拍照出片", "有设计感", "城市地标"],
        "common_budget": 220.0,
        "frequent_districts": ["黄浦区", "徐汇区"],
        "max_wait_preference": 22,
        "walk_preference": "适中",
        "coupon_sensitive": False,
        "summary": "近期偏好咖啡、展览和设计感空间，路线会优先体验质感和拍照友好。",
    },
    "带爸妈轻松型": {
        "search_preferences": ["少走路", "适合老人", "室内", "休息方便"],
        "favorite_categories": ["餐饮", "景点", "咖啡/茶饮", "购物"],
        "favorite_districts": ["黄浦区", "浦东新区", "静安区"],
        "browsed_tags": ["亲子友好", "雨天可去", "交通方便", "安静"],
        "common_budget": 300.0,
        "frequent_districts": ["黄浦区", "浦东新区"],
        "max_wait_preference": 10,
        "walk_preference": "少走路",
        "coupon_sensitive": False,
        "summary": "近期偏好少走路、室内和休息方便的地点，路线会优先轻松与打车友好。",
    },
}

DEFAULT_IMPORTED_PROFILE_RECORDS: list[dict[str, Any]] = [
    {
        "profile_id": "xiangyue-demo",
        "display_name": "Xiangyue 脱敏样本",
        "created_at": "demo-seed",
        "recent_searches": ["瑞幸咖啡", "外滩展览", "深圳上城美食", "轻食", "奈雪的茶"],
        "favorite_pois": ["seed by seed 囍得咖啡酒馆", "gaga 金地威新中心店", "海派光影展馆", "城市买手生活馆"],
        "browsed_pois": ["咖啡", "展览", "拍照出片", "安静", "下午茶"],
        "favorite_categories": ["咖啡/茶饮", "景点", "购物"],
        "favorite_districts": ["黄浦区", "徐汇区"],
        "frequent_districts": ["黄浦区", "徐汇区", "南山区"],
        "budget_preference": 230.0,
        "max_wait_preference": 18,
        "walk_preference": "适中",
        "coupon_sensitive": False,
    },
    {
        "profile_id": "teammate-a-demo",
        "display_name": "队友A 脱敏样本",
        "created_at": "demo-seed",
        "recent_searches": ["优惠套餐", "本帮菜", "不排队", "KTV", "商场停车"],
        "favorite_pois": ["弄堂本帮菜", "低排队火锅", "南京东路商场", "室内娱乐"],
        "browsed_pois": ["性价比高", "基本不用等位", "朋友聚餐", "雨天可去"],
        "favorite_categories": ["餐饮", "娱乐", "购物"],
        "favorite_districts": ["黄浦区", "静安区"],
        "frequent_districts": ["黄浦区", "静安区"],
        "budget_preference": 160.0,
        "max_wait_preference": 10,
        "walk_preference": "少走路",
        "coupon_sensitive": True,
    },
]

FORBIDDEN_PROFILE_KEYS = {
    "password",
    "passwd",
    "cookie",
    "token",
    "authorization",
    "phone",
    "mobile",
    "手机号",
    "真实姓名",
    "real_name",
    "account",
    "账号",
    "order_id",
    "订单号",
    "订单",
    "address",
    "精确地址",
}




def normalize_profile_mode(profile_mode: str | None) -> str:
    if profile_mode in PROFILE_CONTEXTS:
        return str(profile_mode)
    return "文艺体验型"


def build_meituan_context(profile_mode: str | None) -> MeituanUserContext:
    normalized = normalize_profile_mode(profile_mode)
    return MeituanUserContext(profile_mode=normalized, **PROFILE_CONTEXTS[normalized])


def safe_slug(text: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in text.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:48] or f"profile-{int(time.time())}"


def clean_text_list(items: list[str], limit: int = 12) -> list[str]:
    cleaned: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in cleaned:
            continue
        cleaned.append(value[:32])
        if len(cleaned) >= limit:
            break
    return cleaned


def infer_categories_from_text(items: list[str]) -> list[str]:
    category_values: list[str] = []
    rules = [
        (POICategory.CAFE.value, ["咖啡", "茶", "奶茶", "甜品", "下午茶"]),
        (POICategory.RESTAURANT.value, ["餐", "饭", "菜", "火锅", "烧烤", "轻食", "美食"]),
        (POICategory.ATTRACTION.value, ["展", "馆", "景点", "外滩", "文化", "美术", "博物"]),
        (POICategory.ENTERTAINMENT.value, ["KTV", "密室", "电影", "玩", "娱乐", "剧本"]),
        (POICategory.SHOPPING.value, ["商场", "购物", "买手", "市集", "逛街"]),
    ]
    for item in items:
        for category, keywords in rules:
            if any(keyword in item for keyword in keywords) and category not in category_values:
                category_values.append(category)
    return category_values


def profile_signal_count(record: dict[str, Any]) -> int:
    list_keys = [
        "recent_searches",
        "favorite_pois",
        "browsed_pois",
        "favorite_categories",
        "favorite_districts",
        "frequent_districts",
    ]
    count = sum(len(record.get(key) or []) for key in list_keys)
    for key in ("budget_preference", "max_wait_preference", "walk_preference", "coupon_sensitive"):
        if record.get(key) not in (None, "", False):
            count += 1
    return count


def load_imported_profile_records() -> list[dict[str, Any]]:
    ensure_data()
    records = [dict(record) for record in DEFAULT_IMPORTED_PROFILE_RECORDS]
    if PROFILE_IMPORTS_PATH.exists():
        try:
            raw = json.loads(PROFILE_IMPORTS_PATH.read_text(encoding="utf-8"))
            imported = raw.get("profiles", []) if isinstance(raw, dict) else []
            if isinstance(imported, list):
                records.extend(record for record in imported if isinstance(record, dict))
        except json.JSONDecodeError:
            return records
    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        profile_id = str(record.get("profile_id") or safe_slug(record.get("display_name", "")))
        record["profile_id"] = profile_id
        deduped[profile_id] = record
    return list(deduped.values())


def save_imported_profile_record(record: dict[str, Any]) -> None:
    ensure_data()
    existing = [
        item for item in load_imported_profile_records()
        if item.get("profile_id") != record.get("profile_id")
        and item.get("created_at") != "demo-seed"
    ]
    existing.append(record)
    PROFILE_IMPORTS_PATH.write_text(
        json.dumps({"profiles": existing}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def imported_profile_view(record: dict[str, Any]) -> ImportedProfileView:
    display_name = str(record.get("display_name") or "脱敏画像")
    count = profile_signal_count(record)
    prefix = "评委即时画像" if str(record.get("profile_id", "")).startswith("judge-session") else "脱敏导入"
    return ImportedProfileView(
        profile_id=str(record.get("profile_id") or safe_slug(display_name)),
        display_name=display_name,
        signal_count=count,
        summary=f"{prefix} · {display_name} · {count} 个信号",
        created_at=record.get("created_at"),
    )


def imported_record_to_context(record: dict[str, Any]) -> MeituanUserContext:
    display_name = str(record.get("display_name") or "脱敏画像")
    recent_searches = clean_text_list(record.get("recent_searches") or [], 10)
    favorite_pois = clean_text_list(record.get("favorite_pois") or [], 12)
    browsed_pois = clean_text_list(record.get("browsed_pois") or [], 12)
    explicit_categories = clean_text_list(record.get("favorite_categories") or [], 8)
    inferred_categories = infer_categories_from_text([*recent_searches, *favorite_pois, *browsed_pois])
    category_values = {category.value for category in POICategory}
    favorite_categories = [
        category for category in [*explicit_categories, *inferred_categories]
        if category in category_values
    ]
    if not favorite_categories:
        favorite_categories = ["餐饮", "咖啡/茶饮", "景点"]

    favorite_districts = clean_text_list(record.get("favorite_districts") or [], 6)
    frequent_districts = clean_text_list(record.get("frequent_districts") or [], 6)
    if not frequent_districts:
        frequent_districts = favorite_districts or ["黄浦区"]

    signal_count = profile_signal_count(record)
    source_label = "评委即时画像" if str(record.get("profile_id", "")).startswith("judge-session") else "脱敏导入"
    summary = (
        f"{source_label} · {display_name}：基于 {len(recent_searches)} 条偏好、"
        f"{len(favorite_pois)} 个收藏、{len(browsed_pois)} 个浏览信号生成，"
        "不含账号、手机号、cookie 或订单信息。"
    )
    return MeituanUserContext(
        profile_mode=display_name,
        search_preferences=recent_searches or favorite_categories,
        favorite_categories=favorite_categories,
        favorite_districts=favorite_districts or frequent_districts,
        browsed_tags=browsed_pois or recent_searches,
        common_budget=record.get("budget_preference"),
        frequent_districts=frequent_districts,
        max_wait_preference=int(record.get("max_wait_preference") or 20),
        walk_preference=str(record.get("walk_preference") or "适中"),
        coupon_sensitive=bool(record.get("coupon_sensitive")),
        summary=f"{summary} 共 {signal_count} 个画像信号。",
    )


def find_imported_profile(profile_id: str | None) -> dict[str, Any] | None:
    records = load_imported_profile_records()
    if not records:
        return None
    if profile_id:
        for record in records:
            if record.get("profile_id") == profile_id:
                return record
        return None
    return records[0]


def validate_import_payload(request: ManualProfileImportRequest) -> None:
    extra = request.model_extra or {}
    forbidden_keys = [
        key for key in extra
        if any(forbidden in key.lower() or forbidden in key for forbidden in FORBIDDEN_PROFILE_KEYS)
    ]
    if forbidden_keys:
        raise HTTPException(
            status_code=400,
            detail=f"导入数据包含禁止字段：{ '、'.join(forbidden_keys) }。请先脱敏后再导入。",
        )
    all_values = json.dumps(request.model_dump(), ensure_ascii=False)
    if any(token in all_values.lower() for token in ["cookie", "token", "password", "验证码"]):
        raise HTTPException(status_code=400, detail="导入数据疑似包含账号凭证，请删除后再导入。")


def import_request_to_record(request: ManualProfileImportRequest) -> dict[str, Any]:
    display_name = request.display_name.strip()
    record = {
        "profile_id": request.profile_id.strip() if request.profile_id else safe_slug(display_name),
        "display_name": display_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "recent_searches": clean_text_list(request.recent_searches),
        "favorite_pois": clean_text_list(request.favorite_pois),
        "browsed_pois": clean_text_list(request.browsed_pois),
        "favorite_categories": clean_text_list(request.favorite_categories),
        "favorite_districts": clean_text_list(request.favorite_districts),
        "frequent_districts": clean_text_list(request.frequent_districts),
        "budget_preference": request.budget_preference,
        "max_wait_preference": request.max_wait_preference,
        "walk_preference": request.walk_preference,
        "coupon_sensitive": request.coupon_sensitive,
    }
    if profile_signal_count(record) < 3:
        raise HTTPException(status_code=400, detail="至少需要 3 个脱敏画像信号，例如搜索词、收藏 POI 或偏好区域。")
    return record


def resolve_profile_context(
    profile_source: str,
    profile_mode: str | None,
    profile_id: str | None,
) -> tuple[MeituanUserContext, str, str | None, str, int]:
    if profile_source == "official_api":
        raise HTTPException(status_code=400, detail="official_api 当前未启用；需要美团或大赛方授权接口后才能接入。")
    if profile_source == "manual_import":
        record = find_imported_profile(profile_id)
        if record:
            context = imported_record_to_context(record)
            view = imported_profile_view(record)
            source_label = "评委即时画像" if view.profile_id.startswith("judge-session") else "脱敏导入"
            return context, "manual_import", view.profile_id, f"{source_label} · {view.display_name} · {view.signal_count} 个信号", view.signal_count
    context = build_meituan_context(profile_mode)
    return context, "preset", None, f"模拟画像 · {context.profile_mode}", profile_signal_count(PROFILE_CONTEXTS[context.profile_mode])


def profile_with_context(profile: UserProfile, context: MeituanUserContext) -> UserProfile:
    merged = profile.model_copy(deep=True)
    for category in context.favorite_categories:
        if category not in merged.preferred_categories:
            merged.preferred_categories.append(category)
    merged.avg_budget = merged.avg_budget or context.common_budget
    if context.profile_mode == "带爸妈轻松型":
        merged.travel_style = "轻松"
    elif context.profile_mode == "低排队务实型":
        merged.travel_style = "不踩雷"
    else:
        merged.travel_style = "文艺"
    return merged


def intent_with_context(
    intent: ParsedIntent,
    context: MeituanUserContext,
    route_context: RouteContext | None = None,
) -> ParsedIntent:
    next_intent = intent.model_copy(deep=True)
    constraints = next_intent.constraints
    constraints.max_wait_minutes = min(constraints.max_wait_minutes, context.max_wait_preference)
    constraints.budget_per_person = constraints.budget_per_person or context.common_budget
    if route_context and route_context.transport_strategy:
        constraints.transport_mode = route_context.transport_strategy
    if route_context:
        if route_context.fixed_start_poi_id:
            next_intent.extracted_preferences["fixed_start_poi_id"] = route_context.fixed_start_poi_id
        if route_context.pinned_policy:
            next_intent.extracted_preferences["pinned_policy"] = route_context.pinned_policy
    if context.walk_preference == "少走路":
        constraints.max_walk_minutes = min(constraints.max_walk_minutes, 10)
        if not (route_context and route_context.transport_strategy):
            constraints.transport_mode = "短步行+打车"
    explicit_context_location = bool(
        route_context
        and (
            route_context.city_hint
            or route_context.anchor_text
            or route_context.anchor_location
            or route_context.selected_pois
        )
    )
    normalized_city = normalize_city_hint(constraints.city or next_intent.city)
    is_non_shanghai_city = bool(normalized_city and normalized_city != "上海")
    profile_districts = set(context.favorite_districts + context.frequent_districts)
    if explicit_context_location or is_non_shanghai_city:
        constraints.preferred_districts = [
            district
            for district in constraints.preferred_districts
            if district not in profile_districts
        ]
    if not constraints.preferred_districts and not explicit_context_location and not is_non_shanghai_city:
        constraints.preferred_districts = context.frequent_districts[:2]

    category_values = {category.value for category in constraints.preferred_categories}
    for category_text in context.favorite_categories:
        if category_text in {category.value for category in POICategory} and category_text not in category_values:
            constraints.preferred_categories.append(POICategory(category_text))
            category_values.add(category_text)

    if context.profile_mode == "带爸妈轻松型":
        next_intent.extracted_preferences["travel_style"] = "轻松"
        special = next_intent.extracted_preferences.get("special_requirements", "")
        next_intent.extracted_preferences["special_requirements"] = "、".join(filter(None, [special if special != "无" else "", "爸妈", "少走路"]))
    elif context.profile_mode == "低排队务实型":
        next_intent.extracted_preferences["travel_style"] = "不踩雷"
    else:
        next_intent.extracted_preferences["travel_style"] = "文艺"
    return next_intent


