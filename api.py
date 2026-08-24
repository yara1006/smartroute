from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from core.agents.intent_parser import IntentParserAgent
from core.agents.poi_retriever import POIRetrieverAgent
from core.agents.route_intent_router import RouteIntentRouterAgent
from core.agents.route_planner import RoutePlannerAgent
from core.memory.user_profile import UserProfileManager
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
from core.rag.vector_store import POIVectorStore, haversine_km, transit_minutes
from core.services.amap_client import (
    AMapAnchor,
    AMapClient,
    AMapRouteSegment,
    fallback_pois_around_anchor,
    normalize_city_hint,
    resolve_known_anchor,
)
from data.seed_db import generate_mock_pois, generate_reviews


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
POI_PATH = DATA_DIR / "pois.json"
INDEX_DIR = DATA_DIR / "local_index"
PROFILE_DB_PATH = DATA_DIR / "user_profiles.db"
PROFILE_IMPORTS_PATH = DATA_DIR / "profile_imports.json"
load_dotenv(BASE_DIR / ".env")


class PlanRequest(BaseModel):
    query: str = Field(min_length=2)
    user_id: str = "demo-user"
    n_routes: int = Field(default=2, ge=1, le=3)
    profile_mode: str = "文艺体验型"
    profile_source: Literal["preset", "manual_import", "official_api"] = "preset"
    profile_id: str | None = None
    route_context: RouteContext | None = None


class RouteIntentRequest(BaseModel):
    query: str = Field(min_length=1)
    source: str = "xiaotuan"
    context: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    previous_intent: RouteIntentResult | None = None
    user_reply_type: Literal["free_text", "chip", "confirm_route", "skip"] = "free_text"


class SearchPreviewRequest(BaseModel):
    query: str = Field(min_length=1)
    history_terms: list[str] = Field(default_factory=list)
    city_hint: str | None = None
    user_id: str = "demo-user"
    profile_mode: str = "文艺体验型"
    profile_source: Literal["preset", "manual_import", "official_api"] = "preset"
    profile_id: str | None = None


class CandidateView(BaseModel):
    poi: POI
    score: float
    reason: str


class SearchAnchorView(BaseModel):
    text: str
    city: str
    latitude: float
    longitude: float
    source: str


class SearchPreviewResponse(BaseModel):
    anchor: SearchAnchorView | None = None
    candidates: list[CandidateView]
    route_context: RouteContext
    trigger_title: str
    trigger_text: str
    warnings: list[str] = Field(default_factory=list)


class RouteInsight(BaseModel):
    route_id: str
    confidence_score: int
    constraint_hits: list[str]
    budget_left: float | None
    wait_status: str
    walk_intensity: str
    crowd_fit: str
    weather_fit: str
    explanation: str
    risks: list[str] = Field(default_factory=list)


class RouteCompleteness(BaseModel):
    stop_count: int
    has_meal: bool
    has_culture_or_entertainment: bool
    is_complete: bool
    notes: list[str] = Field(default_factory=list)


class ProfileInfluence(BaseModel):
    signal: str
    source: str
    effect: str
    matched_pois: list[str] = Field(default_factory=list)
    weight: str = "中"


class FollowUpOption(BaseModel):
    label: str
    instruction: str
    expected_effect: str


class FollowUp(BaseModel):
    question: str
    options: list[FollowUpOption]
    reason: str


class RouteMetrics(BaseModel):
    stop_count: int
    total_time_minutes: int
    total_cost_per_person: float
    total_wait_minutes: int
    total_transit_minutes: int


class MetricDeltas(BaseModel):
    stop_count: int
    total_time_minutes: int
    total_cost_per_person: float
    total_wait_minutes: int
    total_transit_minutes: int


class ChangedStop(BaseModel):
    order: int
    action: str
    before_poi: str | None = None
    after_poi: str | None = None
    explanation: str


class AgentTraceStep(BaseModel):
    step: str
    tool: str
    input: str
    output: str
    status: Literal["success", "partial", "fallback", "failed"] = "success"


class RouteView(BaseModel):
    route: Route
    insight: RouteInsight


class PlanResponse(BaseModel):
    user_id: str
    query: str
    intent: ParsedIntent
    profile: UserProfile
    profile_mode: str
    profile_source: str = "preset"
    profile_id: str | None = None
    profile_source_description: str = "模拟画像"
    profile_signal_count: int = 0
    meituan_user_context: MeituanUserContext
    candidates: list[CandidateView]
    routes: list[RouteView]
    trace: list[str]
    planning_time_ms: int
    follow_up_question: str | None = None
    follow_up: FollowUp | None = None
    profile_influence: list[ProfileInfluence] = Field(default_factory=list)
    constraint_conflicts: list[str] = Field(default_factory=list)
    route_completeness: RouteCompleteness | None = None
    tool_trace: list[AgentTraceStep] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    user_id: str = "demo-user"
    route: dict[str, Any]
    feedback: int = Field(ge=-1, le=1)


class ReplaceRequest(BaseModel):
    query: str = Field(min_length=2)
    route: Route
    stop_order: int = Field(ge=1)
    user_id: str = "demo-user"
    profile_mode: str = "文艺体验型"
    profile_source: Literal["preset", "manual_import", "official_api"] = "preset"
    profile_id: str | None = None
    route_context: RouteContext | None = None


class ReplacementOption(BaseModel):
    poi: POI
    score: float
    cost_delta: float
    wait_delta: int
    duration_delta: int
    distance_from_previous_km: float | None
    impact_summary: str


class ReplaceResponse(BaseModel):
    stop_order: int
    current_poi_id: str
    options: list[ReplacementOption]


class AdjustRequest(BaseModel):
    query: str = Field(min_length=2)
    instruction: str = Field(min_length=1)
    route: Route
    user_id: str = "demo-user"
    profile_mode: str = "文艺体验型"
    profile_source: Literal["preset", "manual_import", "official_api"] = "preset"
    profile_id: str | None = None
    route_context: RouteContext | None = None


class AdjustResponse(BaseModel):
    route: RouteView
    adjustment_summary: str
    adjustment_status: Literal["applied", "partial", "not_applied"]
    changed_stop_orders: list[int]
    changed_stops: list[ChangedStop] = Field(default_factory=list)
    before_metrics: RouteMetrics
    after_metrics: RouteMetrics
    metric_deltas: MetricDeltas
    suggested_relaxations: list[str] = Field(default_factory=list)
    adjustment_history_item: str
    planning_time_ms: int
    follow_up_question: str | None = None
    follow_up: FollowUp | None = None
    constraint_conflicts: list[str] = Field(default_factory=list)
    route_completeness: RouteCompleteness
    tool_trace: list[AgentTraceStep] = Field(default_factory=list)


@dataclass
class AdjustmentIntent:
    kind: str
    categories: set[POICategory] | None = None
    target_index: int | None = None
    target_text: str | None = None
    max_count: int | None = None
    source: str = "rules"
    reason: str = "规则兜底识别调整目标"


class ManualProfileImportRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    profile_id: str | None = None
    display_name: str = Field(min_length=2)
    recent_searches: list[str] = Field(default_factory=list)
    favorite_pois: list[str] = Field(default_factory=list)
    browsed_pois: list[str] = Field(default_factory=list)
    favorite_categories: list[str] = Field(default_factory=list)
    favorite_districts: list[str] = Field(default_factory=list)
    frequent_districts: list[str] = Field(default_factory=list)
    budget_preference: float | None = Field(default=None, ge=0)
    max_wait_preference: int = Field(default=20, ge=0, le=120)
    walk_preference: str = "适中"
    coupon_sensitive: bool = False


class ImportedProfileView(BaseModel):
    profile_id: str
    display_name: str
    profile_source: str = "manual_import"
    signal_count: int
    summary: str
    created_at: str | None = None


class ProfileSourceView(BaseModel):
    source: str
    label: str
    enabled: bool
    description: str
    profiles: list[ImportedProfileView] = Field(default_factory=list)


class ProfileSourcesResponse(BaseModel):
    sources: list[ProfileSourceView]


class ProfileImportResponse(BaseModel):
    status: str
    profile: ImportedProfileView
    context: MeituanUserContext
    safety_notice: str


@dataclass
class Agents:
    route_intent_router: RouteIntentRouterAgent
    intent_parser: IntentParserAgent
    poi_retriever: POIRetrieverAgent
    route_planner: RoutePlannerAgent
    profile_manager: UserProfileManager


def ensure_data() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not POI_PATH.exists():
        pois = generate_mock_pois(500)
        POI_PATH.write_text(json.dumps(pois, ensure_ascii=False, indent=2), encoding="utf-8")
        (DATA_DIR / "ugc_reviews.json").write_text(
            json.dumps(generate_reviews(pois), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@lru_cache(maxsize=1)
def load_poi_database() -> dict[str, POI]:
    ensure_data()
    raw = json.loads(POI_PATH.read_text(encoding="utf-8"))
    return {item["id"]: POI(**item) for item in raw}


@lru_cache(maxsize=1)
def load_vector_store() -> POIVectorStore:
    ensure_data()
    store = POIVectorStore(str(INDEX_DIR))
    if store.count == 0:
        raw = json.loads(POI_PATH.read_text(encoding="utf-8"))
        store.index_pois(raw)
    return store


@lru_cache(maxsize=1)
def load_agents() -> Agents:
    poi_db = load_poi_database()
    vector_store = load_vector_store()
    return Agents(
        route_intent_router=RouteIntentRouterAgent(),
        intent_parser=IntentParserAgent(),
        poi_retriever=POIRetrieverAgent(vector_store, poi_db),
        route_planner=RoutePlannerAgent(poi_db),
        profile_manager=UserProfileManager(str(PROFILE_DB_PATH)),
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


def extract_anchor_text(query: str, route_context: RouteContext | None = None) -> str | None:
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


def trace_step(step: str, tool: str, input_text: str, output: str, status: str = "success") -> AgentTraceStep:
    normalized = status if status in {"success", "partial", "fallback", "failed"} else "success"
    return AgentTraceStep(
        step=step,
        tool=tool,
        input=input_text[:180],
        output=output[:220],
        status=normalized,  # type: ignore[arg-type]
    )


def build_plan_tool_trace(
    intent: ParsedIntent,
    candidates: list[tuple[POI, float]],
    routes: list[Route],
    context: MeituanUserContext,
    anchor: AMapAnchor | None,
    amap_client: AMapClient,
) -> list[AgentTraceStep]:
    first_route = routes[0] if routes else None
    amap_segments = sum(
        1
        for segment in (first_route.transit_segments if first_route else [])
        if str(segment.get("source", "")).startswith("amap")
    )
    return [
        trace_step(
            "1",
            "ParseIntent",
            intent.extracted_preferences.get("raw_query", ""),
            f"{intent.parser_source} · {intent.parser_reason} · 置信度 {intent.parser_confidence:.2f}",
            "success" if intent.parser_source == "llm" else "fallback",
        ),
        trace_step(
            "2",
            "BuildSessionProfile",
            context.profile_mode,
            f"{context.summary}；交通偏好 {context.walk_preference}，排队≤{context.max_wait_preference}分钟",
        ),
        trace_step(
            "3",
            "SearchPOI",
            anchor.text if anchor else "本地索引",
            f"{'高德/锚点' if anchor else '本地RAG'}候选 {len(candidates)} 个",
            "success" if candidates else "failed",
        ),
        trace_step(
            "4",
            "PlanRoute",
            intent.constraints.transport_mode,
            f"生成 {len(routes)} 条路线，主路线 {len(first_route.stops) if first_route else 0} 个 POI",
            "success" if first_route else "failed",
        ),
        trace_step(
            "5",
            "MapDirections",
            "AMAP_WEB_SERVICE_KEY",
            (
                f"高德分段 {amap_segments} 段，策略 {intent.constraints.transport_mode}"
                if amap_client.enabled
                else "未配置高德 Web 服务 Key，使用本地估算路径"
            ),
            "success" if amap_segments else "fallback",
        ),
    ]


def classify_adjustment_with_deepseek(
    instruction: str,
    route: Route,
) -> tuple[str, set[POICategory] | None, str, str] | None:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat").strip() or "deepseek-chat"
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "optimize_wait",
                "description": "减少排队/等位时间",
                "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "optimize_budget",
                "description": "降低人均预算或提高性价比",
                "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "optimize_walk",
                "description": "减少步行/移动强度",
                "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_category",
                "description": "加入咖啡、餐饮、展览、娱乐等类型 POI",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": ["餐饮", "咖啡/茶饮", "景点", "娱乐"]},
                        "reason": {"type": "string"},
                    },
                },
            },
        },
    ]
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=5.0)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是 SmartRoute 的调整工具选择器。根据用户调整指令选择最合适的一个工具。",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": instruction,
                            "current_route": [
                                {
                                    "name": stop.poi.name,
                                    "category": stop.poi.category.value,
                                    "wait": stop.wait_minutes,
                                    "price": stop.poi.price_per_person,
                                    "transit": stop.transit_minutes,
                                }
                                for stop in route.stops
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            tools=tools,
            tool_choice="auto",
            temperature=0,
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            return None
        call = tool_calls[0]
        name = call.function.name
        args = json.loads(call.function.arguments or "{}")
        reason = str(args.get("reason") or "DeepSeek ToolUse 选择调整工具")
        if name == "optimize_wait":
            return "wait", None, "llm_tool", reason
        if name == "optimize_budget":
            return "cheaper", None, "llm_tool", reason
        if name == "optimize_walk":
            return "walk", None, "llm_tool", reason
        if name == "add_category":
            category_text = str(args.get("category") or "景点")
            try:
                return "add", {POICategory(category_text)}, "llm_tool", reason
            except ValueError:
                return "add", {POICategory.ATTRACTION}, "llm_tool", reason
    except Exception:
        return None
    return None


def build_trace(
    intent: ParsedIntent,
    candidates: list[tuple[POI, float]],
    routes: list[Route],
    context: MeituanUserContext | None = None,
) -> list[str]:
    constraints = intent.constraints
    district = "、".join(constraints.preferred_districts) if constraints.preferred_districts else f"全{intent.city}"
    categories = "、".join(category.value for category in constraints.preferred_categories)
    trace = [
        f"解析需求：{district}，{constraints.total_time_hours:g} 小时，{constraints.party_size} 人，预算 {constraints.budget_per_person or '不限'}。",
    ]
    if context:
        trace.append(f"读取画像：{context.profile_mode}，{context.summary}")
    trace.extend([
        f"检索 POI：按 {categories or '综合偏好'}、评分、价格、等待时间筛出 {len(candidates)} 个候选。",
        f"路线生成：组合 {len(routes)} 条方案，并计算总时长、预算、排队和交通时间。",
        "个性化记忆：喜欢/不合适会写入 SQLite 用户画像，下次检索自动调整权重。",
    ])
    return trace


app = FastAPI(
    title="SmartRoute AI API",
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    agents = load_agents()
    amap_client = AMapClient()
    return {
        "status": "ok",
        "poi_count": len(load_poi_database()),
        "index_count": agents.poi_retriever.vector_store.count,
        "amap_web_service": "configured" if amap_client.enabled else "missing",
        "deepseek": "configured" if os.getenv("DEEPSEEK_API_KEY", "").strip() else "rules_fallback",
    }


@app.get("/api/examples")
def examples() -> dict[str, list[str]]:
    return {
        "examples": [
            "我下午要去深圳大学附近玩3个小时，帮我规划一个路线",
            "我下午要去外滩玩3个小时，帮我规划一个路线",
            "想吃上海特色，但不想排队超过15分钟，4个人，晚上6点出发",
            "带爸妈在上海玩半天，少走路，轻松一点，预算人均300",
            "下午茶加逛街，安静有设计感，最好在静安寺附近",
        ]
    }


@app.post("/api/route-intent", response_model=RouteIntentResult)
def route_intent(request: RouteIntentRequest) -> RouteIntentResult:
    agents = load_agents()
    return agents.route_intent_router.route(
        request.query,
        source=request.source,
        context=request.context,
        previous_intent=request.previous_intent,
        conversation_id=request.conversation_id,
        user_reply_type=request.user_reply_type,
    )


@app.post("/api/search-preview", response_model=SearchPreviewResponse)
def search_preview(request: SearchPreviewRequest) -> SearchPreviewResponse:
    agents = load_agents()
    amap_client = AMapClient()
    meituan_context, profile_source, resolved_profile_id, _, _ = resolve_profile_context(
        request.profile_source,
        request.profile_mode,
        request.profile_id,
    )
    profile = agents.profile_manager.get_profile(request.user_id)
    combined_query = " ".join([request.query, *request.history_terms]).strip()
    intent = agents.intent_parser.parse(combined_query, user_profile=profile.model_dump())
    initial_context = RouteContext(
        source="search",
        city_hint=request.city_hint or city_hint_from(combined_query, intent),
        anchor_text=extract_anchor_text(request.query) or extract_anchor_text(combined_query),
        pinned_policy="soft",
    )
    intent = intent_with_context(intent, meituan_context, initial_context)
    pseudo_request = PlanRequest(
        query=combined_query,
        user_id=request.user_id,
        n_routes=1,
        profile_mode=request.profile_mode,
        profile_source=profile_source,
        profile_id=resolved_profile_id,
        route_context=initial_context,
    )
    candidates, _, anchor, context_trace = build_dynamic_candidates(
        pseudo_request,
        intent,
        meituan_context,
        amap_client,
        allow_anchor_fallback=True,
    )
    candidates = apply_context_to_candidates(candidates, meituan_context)
    selected_pois = default_search_selected_pois(candidates)
    city_hint = normalize_city_hint(anchor.city) if anchor else normalize_city_hint(initial_context.city_hint)
    route_context = initial_context.model_copy(
        update={
            "city_hint": city_hint or initial_context.city_hint,
            "anchor_text": anchor.text if anchor else initial_context.anchor_text,
            "anchor_location": anchor.location if anchor else initial_context.anchor_location,
            "selected_pois": selected_pois,
            "pinned_policy": "soft",
        }
    )
    anchor_view = None
    if anchor:
        anchor_view = SearchAnchorView(
            text=anchor.text,
            city=city_hint or anchor.city,
            latitude=anchor.location.latitude,
            longitude=anchor.location.longitude,
            source=anchor.source,
        )
    warnings = [note for note in context_trace if "失败" in note or "不足" in note or "兜底" in note]
    if not candidates:
        warnings.append("搜索页没有召回可串联 POI，可换一个商圈、放宽区域或稍后重试高德服务。")
    trigger_count = len(selected_pois) or min(len(candidates), 4)
    return SearchPreviewResponse(
        anchor=anchor_view,
        candidates=[build_candidate_view(poi, score) for poi, score in candidates[:8]],
        route_context=route_context,
        trigger_title=f"SmartRoute 已发现 {trigger_count} 个可串联地点",
        trigger_text=(
            f"根据“{request.query}”和历史搜索偏好，先召回附近真实 POI，"
            "再优先参考你勾选的地点生成可执行安排；冲突项会自动舍弃。"
        ),
        warnings=list(dict.fromkeys(warnings))[:4],
    )


@app.get("/api/profile-sources", response_model=ProfileSourcesResponse)
def profile_sources() -> ProfileSourcesResponse:
    preset_profiles = [
        ImportedProfileView(
            profile_id=mode,
            display_name=mode,
            profile_source="preset",
            signal_count=profile_signal_count(context),
            summary=f"模拟画像 · {context['summary']}",
            created_at=None,
        )
        for mode, context in PROFILE_CONTEXTS.items()
    ]
    manual_profiles = [imported_profile_view(record) for record in load_imported_profile_records()]
    return ProfileSourcesResponse(
        sources=[
            ProfileSourceView(
                source="preset",
                label="模拟画像",
                enabled=True,
                description="内置三种演示画像，用于稳定展示差异化路线。",
                profiles=preset_profiles,
            ),
            ProfileSourceView(
                source="manual_import",
                label="脱敏真实画像",
                enabled=True,
                description="由用户手动整理搜索、收藏、浏览偏好后导入，不包含账号凭证或订单隐私。",
                profiles=manual_profiles,
            ),
            ProfileSourceView(
                source="official_api",
                label="官方授权 API",
                enabled=False,
                description="预留接入位；只有拿到美团或大赛方授权接口后启用。",
                profiles=[],
            ),
        ]
    )


@app.post("/api/profile/import", response_model=ProfileImportResponse)
def import_profile(request: ManualProfileImportRequest) -> ProfileImportResponse:
    validate_import_payload(request)
    record = import_request_to_record(request)
    save_imported_profile_record(record)
    view = imported_profile_view(record)
    return ProfileImportResponse(
        status="ok",
        profile=view,
        context=imported_record_to_context(record),
        safety_notice="已保存为脱敏导入画像；未收集账号、密码、cookie、手机号或订单号。",
    )


@app.post("/api/plan", response_model=PlanResponse)
def plan_route(request: PlanRequest) -> PlanResponse:
    started = time.perf_counter()
    agents = load_agents()
    amap_client = AMapClient()
    meituan_context, profile_source, resolved_profile_id, source_description, signal_count = resolve_profile_context(
        request.profile_source,
        request.profile_mode,
        request.profile_id,
    )
    profile = agents.profile_manager.get_profile(request.user_id)
    intent = agents.intent_parser.parse(request.query, user_profile=profile.model_dump())
    intent = intent_with_context(intent, meituan_context, request.route_context)
    live_location_required = requires_live_location_data(request.query, intent, request.route_context)
    agents.profile_manager.infer_profile_from_chat(request.user_id, intent.extracted_preferences)
    profile = profile_with_context(agents.profile_manager.get_profile(request.user_id), meituan_context)
    dynamic_candidates, pinned_pois, anchor, context_trace = build_dynamic_candidates(
        request,
        intent,
        meituan_context,
        amap_client,
        allow_anchor_fallback=True,
    )
    if dynamic_candidates:
        candidates = dynamic_candidates
    elif live_location_required:
        candidates = [(poi, 3.0) for poi in pinned_pois]
        context_trace.append("真实地点模式：高德未返回可用候选，未使用本地 RAG 回退。请检查高德 Web 服务 Key、服务权限或地点解析。")
    else:
        candidates = agents.poi_retriever.retrieve(intent, user_profile=profile)
    candidates = apply_context_to_candidates(candidates, meituan_context)
    routes = agents.route_planner.plan(
        intent,
        candidates,
        user_profile=profile,
        n_routes=request.n_routes,
        pinned_pois=pinned_pois,
    )
    routes = [
        enrich_route_with_amap_segments(route, amap_client, intent.constraints.transport_mode)
        for route in routes
    ]
    for route in routes:
        if anchor:
            if not amap_client.enabled:
                route.warnings = list(dict.fromkeys([*route.warnings, "未配置高德 Web 服务 Key，已使用锚点附近本地兜底 POI 和直线/估算路径。"]))[:5]
            elif all(stop.poi.source != "amap" for stop in route.stops):
                route.warnings = list(dict.fromkeys([*route.warnings, "高德周边 POI 结果不足，已混合本地兜底候选。"]))[:5]
    route_views = [RouteView(route=route, insight=route_insight(route, intent)) for route in routes]
    selected_route_view = route_views[0] if route_views else None
    selected_route = selected_route_view.route if selected_route_view else None
    conflicts = build_constraint_conflicts(selected_route, intent)
    follow_up = build_follow_up(selected_route_view, intent, conflicts, meituan_context)
    planning_time_ms = int((time.perf_counter() - started) * 1000)
    return PlanResponse(
        user_id=request.user_id,
        query=request.query,
        intent=intent,
        profile=profile,
        profile_mode=meituan_context.profile_mode,
        profile_source=profile_source,
        profile_id=resolved_profile_id,
        profile_source_description=source_description,
        profile_signal_count=signal_count,
        meituan_user_context=meituan_context,
        candidates=[build_candidate_view(poi, score) for poi, score in candidates[:12]],
        routes=route_views,
        trace=[*build_trace(intent, candidates, routes, meituan_context), *context_trace],
        planning_time_ms=planning_time_ms,
        follow_up_question=follow_up.question,
        follow_up=follow_up,
        profile_influence=build_profile_influence(meituan_context, selected_route),
        constraint_conflicts=conflicts,
        route_completeness=build_route_completeness(selected_route),
        tool_trace=build_plan_tool_trace(intent, candidates, routes, meituan_context, anchor, amap_client),
    )


@app.post("/api/adjust", response_model=AdjustResponse)
def adjust_route(request: AdjustRequest) -> AdjustResponse:
    started = time.perf_counter()
    agents = load_agents()
    amap_client = AMapClient()
    meituan_context, _, _, _, _ = resolve_profile_context(
        request.profile_source,
        request.profile_mode,
        request.profile_id,
    )
    profile = profile_with_context(agents.profile_manager.get_profile(request.user_id), meituan_context)
    intent = agents.intent_parser.parse(f"{request.query}。调整要求：{request.instruction}", user_profile=profile.model_dump())
    intent = intent_with_context(intent, meituan_context, request.route_context)
    pseudo_plan_request = PlanRequest(
        query=request.query,
        user_id=request.user_id,
        n_routes=1,
        profile_mode=request.profile_mode,
        profile_source=request.profile_source,
        profile_id=request.profile_id,
        route_context=request.route_context,
    )
    dynamic_candidates, context_pinned_pois, anchor, context_trace = build_dynamic_candidates(
        pseudo_plan_request,
        intent,
        meituan_context,
        amap_client,
        allow_anchor_fallback=True,
    )
    if dynamic_candidates:
        candidates = dynamic_candidates
    elif requires_live_location_data(request.query, intent, request.route_context):
        candidates = []
        context_trace.append("真实地点模式：高德未返回可用调整候选，未使用本地 RAG 回退。")
    else:
        candidates = agents.poi_retriever.retrieve(intent, user_profile=profile, max_candidates=60)
    candidates = apply_context_to_candidates(candidates, meituan_context)
    hard_pinned_pois = context_pinned_pois or fixed_start_pois_from_route(request.route_context, request.route)

    llm_adjustment = classify_adjustment_with_deepseek(request.instruction, request.route)
    adjustment_intent = parse_adjustment_intent(request.instruction, request.route, llm_adjustment)
    kind = adjustment_intent.kind
    categories = adjustment_intent.categories
    adjustment_source = adjustment_intent.source
    adjustment_reason = adjustment_intent.reason
    if kind == "avoid_category" and categories:
        for category in categories:
            if category not in intent.constraints.avoid_categories:
                intent.constraints.avoid_categories.append(category)
    if kind in {"avoid_category", "reduce_category"} and categories and anchor:
        replacement_categories = [
            category
            for category in [POICategory.RESTAURANT, POICategory.ATTRACTION, POICategory.SHOPPING, POICategory.ENTERTAINMENT]
            if category not in categories
        ]
        existing_categories = {poi.category for poi, _ in candidates if poi.category not in categories}
        needs_role_supplement = (
            POICategory.CAFE in categories
            and POICategory.RESTAURANT not in existing_categories
        ) or not existing_categories.intersection({POICategory.ATTRACTION, POICategory.SHOPPING, POICategory.ENTERTAINMENT})
        if needs_role_supplement:
            existing_candidate_ids = {poi.id for poi, _ in candidates}
            supplemental_pois = fallback_pois_around_anchor(anchor, replacement_categories, count_per_category=1)
            added_count = 0
            for poi in supplemental_pois:
                if poi.id in existing_candidate_ids:
                    continue
                candidates.append((poi, 2.45))
                added_count += 1
            if added_count:
                context_trace.append(f"调整兜底候选：为避开 {'、'.join(category.value for category in categories)} 补充 {added_count} 个锚点附近替代角色。")
    if adjustment_intent.target_index is not None:
        target_index = adjustment_intent.target_index
    elif kind == "add":
        target_index = choose_add_target(request.route, categories)
    else:
        target_index = choose_adjustment_target(request.route, kind)
    if adjustment_intent.target_index is None and kind in {"avoid_category", "reduce_category"}:
        candidate = None
    else:
        candidate = find_adjustment_candidate(request.route, candidates, kind, target_index, categories)
    if candidate is None and kind == "add" and categories and anchor and amap_client.enabled:
        direct_terms = adjustment_search_terms(request.instruction, categories)
        direct_pois = amap_client.search_pois(anchor, list(categories), keywords=direct_terms, radius_meters=3000, limit_per_category=8)
        if direct_pois:
            existing_candidate_ids = {poi.id for poi, _ in candidates}
            for poi in direct_pois:
                if poi.id not in existing_candidate_ids:
                    candidates.append((poi, 2.8))
            candidate = find_adjustment_candidate(request.route, candidates, kind, target_index, categories)
            context_trace.append(
                f"调整专用召回：围绕 {anchor.text} 用 {'、'.join(direct_terms[:4])} 追加 {len(direct_pois)} 个候选。"
            )
    before_metrics = route_metrics(request.route)
    next_pois = [stop.poi for stop in request.route.stops]
    should_rebuild_route = kind == "walk" or candidate is not None
    route_build_failed = False

    if kind == "add" and candidate:
        if len(next_pois) < 5:
            next_pois.append(candidate)
        else:
            next_pois[target_index] = candidate
    elif candidate:
        next_pois[target_index] = candidate

    if kind == "walk":
        next_pois = agents.route_planner._nearest_neighbor_order(next_pois)

    adjusted_route = None
    if should_rebuild_route:
        adjusted_route = agents.route_planner.build_route_from_pois(intent, next_pois, "实时调整")
        if (
            kind == "add"
            and candidate
            and len(request.route.stops) < 5
            and (adjusted_route is None or not add_intent_satisfied(categories, adjusted_route))
        ):
            replacement_pois = [stop.poi for stop in request.route.stops]
            replacement_pois[target_index] = candidate
            adjusted_route = agents.route_planner.build_route_from_pois(intent, replacement_pois, "实时调整")
        if adjusted_route is None and kind in {"focus", "reduce_category", "avoid_category"} and candidates:
            repaired_pois = agents.route_planner._repair_selected_stops(
                intent,
                next_pois,
                candidates,
                max_stops=max(3, len(request.route.stops)),
                budget=intent.constraints.budget_per_person,
                pinned_pois=hard_pinned_pois,
            )
            repaired_route = agents.route_planner.build_route_from_pois(intent, repaired_pois, "实时调整")
            if repaired_route is not None:
                adjusted_route = repaired_route
        if adjusted_route is not None:
            adjusted_route = enrich_route_with_amap_segments(adjusted_route, amap_client, intent.constraints.transport_mode)
            structure_issues = agents.route_planner._structure_warnings(intent, [stop.poi for stop in adjusted_route.stops])
            if structure_issues and candidates:
                repaired_pois = agents.route_planner._repair_selected_stops(
                    intent,
                    [stop.poi for stop in adjusted_route.stops],
                    candidates,
                    max_stops=max(3, len(adjusted_route.stops)),
                    budget=intent.constraints.budget_per_person,
                    pinned_pois=hard_pinned_pois,
                )
                repaired_route = agents.route_planner.build_route_from_pois(intent, repaired_pois, "实时调整")
                if repaired_route is not None:
                    repaired_issues = agents.route_planner._structure_warnings(intent, [stop.poi for stop in repaired_route.stops])
                    if len(repaired_issues) < len(structure_issues):
                        adjusted_route = enrich_route_with_amap_segments(repaired_route, amap_client, intent.constraints.transport_mode)
    if adjusted_route is None:
        route_build_failed = should_rebuild_route
        adjusted_route = request.route.model_copy(deep=True)
        if route_build_failed:
            adjusted_route.warnings = list(dict.fromkeys([*adjusted_route.warnings, "当前调整会破坏路线完整性，已保留原路线。"]))

    changed_orders = [
        index + 1
        for index in range(max(len(request.route.stops), len(adjusted_route.stops)))
        if index >= len(request.route.stops)
        or index >= len(adjusted_route.stops)
        or request.route.stops[index].poi.id != adjusted_route.stops[index].poi.id
    ]
    changed_stops = build_changed_stops(request.route, adjusted_route, changed_orders)
    after_metrics = route_metrics(adjusted_route)
    deltas = metric_deltas(before_metrics, after_metrics)
    status = adjustment_status_for(kind, request.route, adjusted_route, changed_stops, deltas, candidate)
    if route_build_failed:
        status = "not_applied"
    elif kind == "add" and not add_intent_satisfied(categories, adjusted_route):
        status = "not_applied"
        adjusted_route.warnings = list(
            dict.fromkeys([*adjusted_route.warnings, "当前调整没有成功加入目标类型站点，已保留路线完整性优先。"])
        )[:5]
    elif status == "applied" and not adjustment_intent_satisfied(adjustment_intent, adjusted_route):
        status = "partial"
    structure_issues = agents.route_planner._structure_warnings(intent, [stop.poi for stop in adjusted_route.stops])
    if structure_issues:
        adjusted_route.warnings = list(dict.fromkeys([*adjusted_route.warnings, *structure_issues]))[:5]
        if status == "applied":
            status = "partial"

    changed_name = candidate.name if candidate else None
    summary = adjustment_summary(kind, request.instruction, changed_name, status, deltas)
    adjusted_route.id = f"{request.route.id}-adj"
    adjusted_route.description = summary
    if status == "not_applied":
        adjusted_route.warnings = list(dict.fromkeys([*adjusted_route.warnings, summary]))[:5]
    else:
        adjusted_route.highlights = list(dict.fromkeys([summary, *adjusted_route.highlights]))[:4]

    route_view = RouteView(route=adjusted_route, insight=route_insight(adjusted_route, intent))
    conflicts = build_constraint_conflicts(adjusted_route, intent)
    follow_up = build_follow_up(route_view, intent, conflicts, meituan_context)
    planning_time_ms = int((time.perf_counter() - started) * 1000)
    search_source = "高德/锚点候选" if dynamic_candidates else "本地RAG候选"
    tool_trace = [
        trace_step(
            "1",
            "ParseAdjustment",
            request.instruction,
            f"{adjustment_source} · {adjustment_reason} · kind={kind}",
            "success" if adjustment_source == "llm_tool" else "fallback",
        ),
        trace_step(
            "2",
            "SearchReplacementPOI",
            search_source,
            f"候选 {len(candidates)} 个；命中 {candidate.name if candidate else '无更优替换项'}",
            "success" if candidate else "partial",
        ),
        trace_step(
            "3",
            "ValidateConstraints",
            f"目标第 {target_index + 1} 站",
            "；".join(conflicts) if conflicts else "路线完整性和主要约束可接受",
            "partial" if conflicts else "success",
        ),
        trace_step(
            "4",
            "UpdateRoute",
            intent.constraints.transport_mode,
            summary,
            "success" if status == "applied" else "partial" if status == "partial" else "failed",
        ),
        trace_step(
            "5",
            "ExplainChanges",
            "metrics",
            f"等位 {deltas.total_wait_minutes:+} 分钟，人均 {deltas.total_cost_per_person:+.0f} 元，移动 {deltas.total_transit_minutes:+} 分钟",
            "success",
        ),
    ]
    if context_trace:
        tool_trace.insert(2, trace_step("2b", "ContextPOISearch", anchor.text if anchor else "无锚点", "；".join(context_trace), "success"))
    return AdjustResponse(
        route=route_view,
        adjustment_summary=summary,
        adjustment_status=status,
        changed_stop_orders=changed_orders,
        changed_stops=changed_stops,
        before_metrics=before_metrics,
        after_metrics=after_metrics,
        metric_deltas=deltas,
        suggested_relaxations=suggested_relaxations_for(kind, status, conflicts),
        adjustment_history_item=f"{request.instruction}：{summary}",
        planning_time_ms=planning_time_ms,
        follow_up_question=follow_up.question,
        follow_up=follow_up,
        constraint_conflicts=conflicts,
        route_completeness=build_route_completeness(adjusted_route) or RouteCompleteness(
            stop_count=0,
            has_meal=False,
            has_culture_or_entertainment=False,
            is_complete=False,
            notes=["调整失败"],
        ),
        tool_trace=tool_trace,
    )


@app.post("/api/feedback")
def feedback(request: FeedbackRequest) -> dict[str, Any]:
    agents = load_agents()
    agents.profile_manager.update_from_route(
        request.user_id,
        request.route,
        feedback=request.feedback,
    )
    profile = agents.profile_manager.get_profile(request.user_id)
    return {"status": "ok", "profile": profile.model_dump(mode="json")}


@app.post("/api/replace", response_model=ReplaceResponse)
def replace_poi(request: ReplaceRequest) -> ReplaceResponse:
    agents = load_agents()
    if request.stop_order > len(request.route.stops):
        raise HTTPException(status_code=404, detail="stop_order 超出当前路线范围")

    current_stop = request.route.stops[request.stop_order - 1]
    current_ids = {stop.poi.id for stop in request.route.stops}
    previous_poi = request.route.stops[request.stop_order - 2].poi if request.stop_order > 1 else None
    amap_client = AMapClient()
    meituan_context, _, _, _, _ = resolve_profile_context(
        request.profile_source,
        request.profile_mode,
        request.profile_id,
    )
    profile = profile_with_context(agents.profile_manager.get_profile(request.user_id), meituan_context)
    intent = agents.intent_parser.parse(request.query, user_profile=profile.model_dump())

    inferred_context = request.route_context or RouteContext(
        source="replace",
        city_hint=normalize_city_hint(current_stop.poi.district) or current_stop.poi.district,
        anchor_text=current_stop.poi.name,
        anchor_location=GeoPoint(latitude=current_stop.poi.latitude, longitude=current_stop.poi.longitude),
    )
    replace_context = inferred_context.model_copy(
        update={
            "anchor_location": inferred_context.anchor_location or GeoPoint(
                latitude=current_stop.poi.latitude,
                longitude=current_stop.poi.longitude,
            ),
            "anchor_text": inferred_context.anchor_text or current_stop.poi.name,
            "city_hint": inferred_context.city_hint or normalize_city_hint(current_stop.poi.district) or current_stop.poi.district,
        }
    )
    intent.constraints.preferred_categories = [current_stop.poi.category]
    intent = intent_with_context(intent, meituan_context, replace_context)
    pseudo_plan_request = PlanRequest(
        query=request.query,
        user_id=request.user_id,
        n_routes=1,
        profile_mode=request.profile_mode,
        profile_source=request.profile_source,
        profile_id=request.profile_id,
        route_context=replace_context,
    )
    dynamic_candidates, _, _, _ = build_dynamic_candidates(
        pseudo_plan_request,
        intent,
        meituan_context,
        amap_client,
        allow_anchor_fallback=True,
    )
    if dynamic_candidates:
        candidates = dynamic_candidates
    elif requires_live_location_data(request.query, intent, replace_context):
        candidates = []
    else:
        candidates = agents.poi_retriever.retrieve(intent, user_profile=profile, max_candidates=40)
    candidates = apply_context_to_candidates(candidates, meituan_context)

    options: list[ReplacementOption] = []
    for poi, score in candidates:
        if poi.id in current_ids or poi.category != current_stop.poi.category:
            continue
        distance = None
        if previous_poi:
            distance = haversine_km(previous_poi.latitude, previous_poi.longitude, poi.latitude, poi.longitude)
            if poi.source != "amap" and distance > 12:
                continue
        cost_delta = round(poi.price_per_person - current_stop.poi.price_per_person, 1)
        wait_delta = poi.avg_wait_minutes - current_stop.wait_minutes
        duration_delta = poi.visit_duration_minutes - current_stop.duration_minutes
        impact = []
        if cost_delta <= 0:
            impact.append(f"人均省 ¥{abs(cost_delta):.0f}")
        else:
            impact.append(f"人均 +¥{cost_delta:.0f}")
        if wait_delta <= 0:
            impact.append(f"少等 {abs(wait_delta)} 分钟")
        else:
            impact.append(f"多等 {wait_delta} 分钟")
        if distance is not None:
            impact.append(f"距上一站 {distance:.1f}km")
        options.append(
            ReplacementOption(
                poi=poi,
                score=round(score, 3),
                cost_delta=cost_delta,
                wait_delta=wait_delta,
                duration_delta=duration_delta,
                distance_from_previous_km=round(distance, 2) if distance is not None else None,
                impact_summary=" · ".join(impact),
            )
        )
        if len(options) >= 6:
            break

    return ReplaceResponse(
        stop_order=request.stop_order,
        current_poi_id=current_stop.poi.id,
        options=options,
    )
