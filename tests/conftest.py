"""Shared test fixtures for SmartRoute test suite."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.models import POI, POICategory, Route, RouteStop


# ── POI Factories ───────────────────────────────────────────────────────

@pytest.fixture()
def make_poi():
    """Factory fixture to create test POIs with sensible defaults."""
    counter = 0

    def _make(
        poi_id: str | None = None,
        name: str = "Test POI",
        category: POICategory = POICategory.RESTAURANT,
        rating: float = 4.5,
        price: float = 80.0,
        wait: int = 10,
        lat: float = 31.23,
        lng: float = 121.47,
        district: str = "黄浦区",
        **kwargs,
    ) -> POI:
        nonlocal counter
        counter += 1
        return POI(
            id=poi_id or f"test-poi-{counter}",
            name=name,
            category=category,
            address=f"{district}测试路{counter}号",
            district=district,
            latitude=lat,
            longitude=lng,
            rating=rating,
            review_count=100,
            price_per_person=price,
            avg_wait_minutes=wait,
            business_hours={"open": "10:00", "close": "22:00"},
            tags=[category.value],
            ugc_summary=f"{name}的测试描述",
            visit_duration_minutes=60,
            **kwargs,
        )

    return _make


@pytest.fixture()
def make_route(make_poi):
    """Factory fixture to create test routes with stops."""

    def _make(
        stops_count: int = 3,
        categories: list[POICategory] | None = None,
    ) -> Route:
        if categories is None:
            categories = [POICategory.CAFE, POICategory.ATTRACTION, POICategory.RESTAURANT]
        route_stops = []
        for i in range(stops_count):
            cat = categories[i % len(categories)]
            poi = make_poi(
                poi_id=f"route-stop-{i}",
                name=f"Stop {i} ({cat.value})",
                category=cat,
                lat=31.23 + i * 0.005,
                lng=121.47 + i * 0.005,
            )
            route_stops.append(
                RouteStop(
                    order=i + 1,
                    poi=poi,
                    arrival_time=f"{14 + i}:00",
                    departure_time=f"{14 + i}:30",
                    duration_minutes=30,
                    wait_minutes=5,
                )
            )
        return Route(
            id="test-route",
            title="测试路线",
            description="用于测试的路线",
            stops=route_stops,
            total_time_minutes=180,
            total_cost_per_person=200.0,
            total_wait_minutes=15,
            total_transit_minutes=30,
        )

    return _make


# ── API Client ──────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    """Create a FastAPI test client."""
    from api import app
    return TestClient(app)


# ── Temp Data Directory ─────────────────────────────────────────────────

@pytest.fixture()
def tmp_data_dir(tmp_path):
    """Provide a temporary data directory for tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "local_index").mkdir()
    return data_dir
