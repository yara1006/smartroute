from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from core.agents.intent_parser import IntentParserAgent
from core.agents.poi_retriever import POIRetrieverAgent
from core.agents.route_intent_router import RouteIntentRouterAgent
from core.agents.route_planner import RoutePlannerAgent
from core.memory.user_profile import UserProfileManager
from core.models import GeoPoint, POI, POICategory, RouteContext, RouteIntentResult, UserProfile
from core.rag.vector_store import POIVectorStore, haversine_km
from core.services.amap_client import AMapAnchor, AMapClient, fallback_pois_around_anchor, normalize_city_hint
from data.seed_db import generate_mock_pois, generate_reviews


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
POI_PATH = DATA_DIR / "pois.json"
INDEX_DIR = DATA_DIR / "local_index"
PROFILE_DB_PATH = DATA_DIR / "user_profiles.db"
PROFILE_IMPORTS_PATH = DATA_DIR / "profile_imports.json"
load_dotenv(BASE_DIR / ".env")


from schemas import (
    AdjustmentIntent,
    AdjustRequest,
    AdjustResponse,
    AgentTraceStep,
    CandidateView,
    ChangedStop,
    FeedbackRequest,
    FollowUp,
    FollowUpOption,
    ImportedProfileView,
    ManualProfileImportRequest,
    MetricDeltas,
    PlanRequest,
    PlanResponse,
    ProfileImportResponse,
    ProfileInfluence,
    ProfileSourceView,
    ProfileSourcesResponse,
    ReplaceRequest,
    ReplaceResponse,
    ReplacementOption,
    RouteCompleteness,
    RouteInsight,
    RouteIntentRequest,
    RouteMetrics,
    RouteView,
    SearchAnchorView,
    SearchPreviewRequest,
    SearchPreviewResponse,
)



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



from services.route_service import (  # noqa: F401
    PROFILE_CONTEXTS,
    DEFAULT_IMPORTED_PROFILE_RECORDS,
    FORBIDDEN_PROFILE_KEYS,
    adjustment_status_for,
    adjustment_summary,
    apply_context_to_candidates,
    build_candidate_view,
    build_changed_stops,
    build_constraint_conflicts,
    build_dynamic_candidates,
    build_follow_up,
    build_plan_tool_trace,
    build_route_completeness,
    build_trace,
    build_profile_influence,
    categories_for_live_route,
    city_hint_from,
    classify_adjustment_with_deepseek,
    context_poi_to_poi,
    default_search_selected_pois,
    enrich_route_with_amap_segments,
    extract_anchor_text,
    find_adjustment_candidate,
    fixed_start_pois_from_route,
    hard_pinned_pois_for_context,
    import_request_to_record,
    imported_profile_view,
    imported_record_to_context,
    infer_categories_from_text,
    intent_with_context,
    is_core_route_stop,
    load_imported_profile_records,
    metric_deltas,
    normalize_profile_mode,
    parse_adjustment_intent,
    poi_to_context_poi,
    profile_signal_count,
    profile_with_context,
    requires_live_location_data,
    resolve_profile_context,
    route_insight,
    route_metrics,
    safe_slug,
    save_imported_profile_record,
    suggested_relaxations_for,
    trace_step,
    validate_import_payload,
    add_intent_satisfied,
    adjustment_intent_satisfied,
    adjustment_search_terms,
    choose_add_target,
    choose_adjustment_target,
    build_meituan_context,
    ensure_data,
)

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
