from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class POICategory(str, Enum):
    RESTAURANT = "餐饮"
    ATTRACTION = "景点"
    SHOPPING = "购物"
    ENTERTAINMENT = "娱乐"
    CAFE = "咖啡/茶饮"
    ACCOMMODATION = "住宿"


class POI(BaseModel):
    id: str
    name: str
    category: POICategory
    address: str
    district: str = "上海"
    latitude: float
    longitude: float
    rating: float = Field(ge=0, le=5)
    review_count: int = Field(ge=0)
    price_per_person: float = Field(ge=0)
    avg_wait_minutes: int = Field(default=0, ge=0)
    business_hours: dict[str, str]
    tags: list[str] = Field(default_factory=list)
    ugc_summary: str
    phone: str | None = None
    images: list[str] = Field(default_factory=list)
    visit_duration_minutes: int = Field(default=60, ge=10)
    source: str = "local"
    external_id: str | None = None
    distance_from_anchor_meters: int | None = None


class UserConstraints(BaseModel):
    city: str = "上海"
    start_location: str | None = None
    start_time: str = "14:00"
    total_time_hours: float = 4.0
    budget_per_person: float | None = None
    max_wait_minutes: int = 30
    max_walk_minutes: int = 20
    party_size: int = 2
    transport_mode: str = "步行+公交"
    preferred_categories: list[POICategory] = Field(default_factory=list)
    avoid_categories: list[POICategory] = Field(default_factory=list)
    must_include_pois: list[str] = Field(default_factory=list)
    preferred_districts: list[str] = Field(default_factory=list)


class RouteStop(BaseModel):
    order: int
    poi: POI
    arrival_time: str
    departure_time: str
    duration_minutes: int
    wait_minutes: int = 0
    transit_to_next: str | None = None
    transit_minutes: int | None = None
    transit_polyline: list[list[float]] = Field(default_factory=list)
    tips: str = ""


class Route(BaseModel):
    id: str
    title: str
    description: str
    stops: list[RouteStop]
    total_time_minutes: int
    total_cost_per_person: float
    total_wait_minutes: int = 0
    total_transit_minutes: int = 0
    map_polyline: list[list[float]] = Field(default_factory=list)
    transit_segments: list[dict[str, Any]] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)


class GeoPoint(BaseModel):
    latitude: float
    longitude: float


class RouteContextPOI(BaseModel):
    id: str | None = None
    name: str
    category: POICategory | str = POICategory.RESTAURANT
    address: str = ""
    district: str = ""
    latitude: float | None = None
    longitude: float | None = None
    rating: float = Field(default=4.5, ge=0, le=5)
    review_count: int = Field(default=0, ge=0)
    price_per_person: float = Field(default=80, ge=0)
    avg_wait_minutes: int = Field(default=10, ge=0)
    business_hours: dict[str, str] = Field(default_factory=lambda: {"open": "10:00", "close": "22:00"})
    tags: list[str] = Field(default_factory=list)
    ugc_summary: str = ""
    visit_duration_minutes: int = Field(default=60, ge=10)
    source: str = "context"
    external_id: str | None = None


class RouteContext(BaseModel):
    source: str = "manual"
    city_hint: str | None = None
    anchor_text: str | None = None
    anchor_location: GeoPoint | None = None
    selected_pois: list[RouteContextPOI] = Field(default_factory=list)
    transport_strategy: str | None = None
    fixed_start_poi_id: str | None = None
    pinned_policy: str | None = None


class UserProfile(BaseModel):
    user_id: str
    preferred_categories: list[str] = Field(default_factory=list)
    disliked_categories: list[str] = Field(default_factory=list)
    avg_budget: float | None = None
    preferred_time_slots: list[str] = Field(default_factory=list)
    travel_style: str | None = None
    visited_poi_ids: list[str] = Field(default_factory=list)
    liked_poi_ids: list[str] = Field(default_factory=list)
    disliked_poi_ids: list[str] = Field(default_factory=list)
    history_routes: list[str] = Field(default_factory=list)


class MeituanUserContext(BaseModel):
    profile_mode: str = "文艺体验型"
    search_preferences: list[str] = Field(default_factory=list)
    favorite_categories: list[str] = Field(default_factory=list)
    favorite_districts: list[str] = Field(default_factory=list)
    browsed_tags: list[str] = Field(default_factory=list)
    common_budget: float | None = None
    frequent_districts: list[str] = Field(default_factory=list)
    max_wait_preference: int = 30
    walk_preference: str = "适中"
    coupon_sensitive: bool = False
    summary: str = ""


class ParsedIntent(BaseModel):
    city: str = "上海"
    query_type: str = "路线规划"
    constraints: UserConstraints
    extracted_preferences: dict[str, Any] = Field(default_factory=dict)
    clarification_needed: bool = False
    clarification_question: str | None = None
    parser_source: str = "rules"
    parser_confidence: float = Field(default=0.72, ge=0, le=1)
    parser_reason: str = "规则解析"
    llm_slots: dict[str, Any] = Field(default_factory=dict)


class RouteIntentResult(BaseModel):
    action: str
    confidence: float = Field(ge=0, le=1)
    reason: str
    detected_slots: dict[str, Any] = Field(default_factory=dict)
    planning_query: str
    source: str = "rules"
    conversation_id: str | None = None
    turn_state: str = "new"
    filled_slots: dict[str, Any] = Field(default_factory=dict)
    missing_slots: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    clarification_options: list[str] = Field(default_factory=list)
    merged_query: str | None = None
    intent_type: str = ""
    anchor_text: str | None = None
    activities: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    negative_reason: str | None = None
    rule_signals: dict[str, Any] = Field(default_factory=dict)
    llm_judgement: dict[str, Any] | None = None
    fusion: dict[str, Any] = Field(default_factory=dict)
    follow_up_question: str | None = None
