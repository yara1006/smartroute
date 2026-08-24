"""SmartRoute Tool trace and DeepSeek classification."""
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


