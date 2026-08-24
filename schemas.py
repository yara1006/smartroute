"""SmartRoute API schemas — Pydantic models for all request/response types."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.models import (
    MeituanUserContext,
    POI,
    POICategory,
    ParsedIntent,
    Route,
    RouteContext,
    RouteIntentResult,
    UserProfile,
)


class PlanRequest(BaseModel):
    """Request body for /api/plan — user query plus profile and routing context."""
    query: str = Field(min_length=2)
    user_id: str = "demo-user"
    n_routes: int = Field(default=2, ge=1, le=3)
    profile_mode: str = "文艺体验型"
    profile_source: Literal["preset", "manual_import", "official_api"] = "preset"
    profile_id: str | None = None
    route_context: RouteContext | None = None


class RouteIntentRequest(BaseModel):
    """Request body for /api/route-intent — classifies whether to open the route plugin."""
    query: str = Field(min_length=1)
    source: str = "xiaotuan"
    context: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    previous_intent: RouteIntentResult | None = None
    user_reply_type: Literal["free_text", "chip", "confirm_route", "skip"] = "free_text"


class SearchPreviewRequest(BaseModel):
    """Request body for /api/search-preview — lightweight POI preview before full planning."""
    query: str = Field(min_length=1)
    history_terms: list[str] = Field(default_factory=list)
    city_hint: str | None = None
    user_id: str = "demo-user"
    profile_mode: str = "文艺体验型"
    profile_source: Literal["preset", "manual_import", "official_api"] = "preset"
    profile_id: str | None = None


class CandidateView(BaseModel):
    """A single POI candidate with relevance score and human-readable reason."""
    poi: POI
    score: float
    reason: str


class SearchAnchorView(BaseModel):
    """Resolved geographic anchor (location + city) used for POI search."""
    text: str
    city: str
    latitude: float
    longitude: float
    source: str


class SearchPreviewResponse(BaseModel):
    """Response for /api/search-preview — anchor, candidate POIs, and trigger copy."""
    anchor: SearchAnchorView | None = None
    candidates: list[CandidateView]
    route_context: RouteContext
    trigger_title: str
    trigger_text: str
    warnings: list[str] = Field(default_factory=list)


class RouteInsight(BaseModel):
    """Qualitative assessment of a generated route — constraint hits, risks, fit scores."""
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
    """Whether a route covers essential roles (meal, culture/entertainment) and stop count."""
    stop_count: int
    has_meal: bool
    has_culture_or_entertainment: bool
    is_complete: bool
    notes: list[str] = Field(default_factory=list)


class ProfileInfluence(BaseModel):
    """How a specific user-profile signal influenced the generated route."""
    signal: str
    source: str
    effect: str
    matched_pois: list[str] = Field(default_factory=list)
    weight: str = "中"


class FollowUpOption(BaseModel):
    """A single chip-style follow-up suggestion shown to the user after a route."""
    label: str
    instruction: str
    expected_effect: str


class FollowUp(BaseModel):
    """Follow-up question and chip options offered to refine the current route."""
    question: str
    options: list[FollowUpOption]
    reason: str


class RouteMetrics(BaseModel):
    """Aggregate numeric metrics for a route (time, cost, wait, transit)."""
    stop_count: int
    total_time_minutes: int
    total_cost_per_person: float
    total_wait_minutes: int
    total_transit_minutes: int


class MetricDeltas(BaseModel):
    """Difference in aggregate metrics between the before and after adjustment routes."""
    stop_count: int
    total_time_minutes: int
    total_cost_per_person: float
    total_wait_minutes: int
    total_transit_minutes: int


class ChangedStop(BaseModel):
    """Description of a single stop that changed during route adjustment."""
    order: int
    action: str
    before_poi: str | None = None
    after_poi: str | None = None
    explanation: str


class AgentTraceStep(BaseModel):
    """One step in the agent tool-call trace shown in the UI."""
    step: str
    tool: str
    input: str
    output: str
    status: Literal["success", "partial", "fallback", "failed"] = "success"


class RouteView(BaseModel):
    """A generated route paired with its qualitative insight assessment."""
    route: Route
    insight: RouteInsight


class PlanResponse(BaseModel):
    """Full response for /api/plan — intent, profile, candidates, routes, and trace."""
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
    """Request body for /api/feedback — user thumbs-up/down on a generated route."""
    user_id: str = "demo-user"
    route: dict[str, Any]
    feedback: int = Field(ge=-1, le=1)


class ReplaceRequest(BaseModel):
    """Request body for /api/replace — find alternatives for a specific route stop."""
    query: str = Field(min_length=2)
    route: Route
    stop_order: int = Field(ge=1)
    user_id: str = "demo-user"
    profile_mode: str = "文艺体验型"
    profile_source: Literal["preset", "manual_import", "official_api"] = "preset"
    profile_id: str | None = None
    route_context: RouteContext | None = None


class ReplacementOption(BaseModel):
    """A candidate POI that could replace a route stop, with cost/wait/duration deltas."""
    poi: POI
    score: float
    cost_delta: float
    wait_delta: int
    duration_delta: int
    distance_from_previous_km: float | None
    impact_summary: str


class ReplaceResponse(BaseModel):
    """Response for /api/replace — ranked replacement options for a given stop."""
    stop_order: int
    current_poi_id: str
    options: list[ReplacementOption]


class AdjustRequest(BaseModel):
    """Request body for /api/adjust — modify an existing route by natural-language instruction."""
    query: str = Field(min_length=2)
    instruction: str = Field(min_length=1)
    route: Route
    user_id: str = "demo-user"
    profile_mode: str = "文艺体验型"
    profile_source: Literal["preset", "manual_import", "official_api"] = "preset"
    profile_id: str | None = None
    route_context: RouteContext | None = None


class AdjustResponse(BaseModel):
    """Full response for /api/adjust — adjusted route, deltas, status, and trace."""
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
    """Structured representation of a route-adjustment command (kind, target, categories)."""
    kind: str
    categories: set[POICategory] | None = None
    target_index: int | None = None
    target_text: str | None = None
    max_count: int | None = None
    source: str = "rules"
    reason: str = "规则兜底识别调整目标"


class ManualProfileImportRequest(BaseModel):
    """Request body for /api/profile/import — desensitized user profile data for manual import."""
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
    """Summary view of a desensitized imported user profile."""
    profile_id: str
    display_name: str
    profile_source: str = "manual_import"
    signal_count: int
    summary: str
    created_at: str | None = None


class ProfileSourceView(BaseModel):
    """Describes one profile source (preset / manual import / official API) with its profiles."""
    source: str
    label: str
    enabled: bool
    description: str
    profiles: list[ImportedProfileView] = Field(default_factory=list)


class ProfileSourcesResponse(BaseModel):
    """Response for /api/profile-sources — all available profile sources and their profiles."""
    sources: list[ProfileSourceView]


class ProfileImportResponse(BaseModel):
    """Response for /api/profile/import — confirmation of a successful profile import."""
    status: str
    profile: ImportedProfileView
    context: MeituanUserContext
    safety_notice: str
