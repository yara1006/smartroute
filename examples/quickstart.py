#!/usr/bin/env python3
"""SmartRoute API examples.

Run against a local backend:
    python -m uvicorn api:app --port 8000
    python examples/quickstart.py
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error

API_BASE = "http://127.0.0.1:8000/api"


def get(path: str) -> dict:
    """GET request."""
    req = urllib.request.Request(f"{API_BASE}{path}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def post(path: str, data: dict) -> dict:
    """POST request."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def example_health():
    """Check service health."""
    print("=== 1. Health Check ===")
    result = get("/health")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def example_plan():
    """Plan a route from natural language."""
    print("\n=== 2. Plan Route ===")
    result = post("/plan", {
        "query": "我下午要去深圳大学附近玩3个小时，帮我规划一个路线",
        "user_id": "example-user",
        "num_routes": 2,
        "profile_source": "preset",
        "profile_id": "low-wait-pragmatic",
        "route_context": {
            "source": "search",
            "city_hint": "深圳",
            "anchor_text": "深圳大学",
        },
    })
    print(f"Routes generated: {len(result.get('routes', []))}")
    print(f"Planning time: {result.get('planning_time_ms', 0)}ms")
    print(f"Parser source: {result.get('intent', {}).get('parser_source', 'unknown')}")
    for i, route in enumerate(result.get("routes", [])[:2]):
        stops = [s["poi"]["name"] for s in route.get("stops", [])]
        print(f"  Route {i+1}: {' -> '.join(stops)}")


def example_adjust():
    """Adjust an existing route."""
    print("\n=== 3. Adjust Route ===")
    # First plan a route
    plan = post("/plan", {
        "query": "深圳大学附近3小时路线",
        "user_id": "example-user",
        "route_context": {"city_hint": "深圳", "anchor_text": "深圳大学"},
    })
    routes = plan.get("routes", [])
    if not routes:
        print("No routes to adjust.")
        return

    route = routes[0]
    result = post("/adjust", {
        "route": route,
        "instruction": "少走路，便宜一点",
        "profile_mode": plan.get("profile_mode", "低排队务实型"),
        "query": plan.get("intent", {}).get("raw_query", "深圳大学附近3小时路线"),
    })
    print(f"Status: {result.get('adjustment_status', 'unknown')}")
    print(f"Changed stops: {len(result.get('changed_stops', []))}")
    deltas = result.get("metric_deltas", {})
    if deltas:
        print(f"Duration delta: {deltas.get('duration_minutes', 0)}min")
        print(f"Cost delta: {deltas.get('total_cost', 0)}元")


def example_search_preview():
    """Search for candidate POIs."""
    print("\n=== 4. Search Preview ===")
    result = post("/search-preview", {
        "query": "深圳大学附近咖啡",
        "history": ["科技园咖啡"],
        "city_hint": "深圳",
    })
    candidates = result.get("candidates", [])
    print(f"Candidates found: {len(candidates)}")
    for c in candidates[:3]:
        print(f"  - {c.get('name', 'unknown')} ({c.get('category', '')})")


def example_route_intent():
    """Check route intent from XiaoTuan query."""
    print("\n=== 5. Route Intent ===")
    result = post("/route-intent", {
        "query": "我下午要去深圳大学附近玩3个小时",
        "source": "xiaotuan",
        "context": {"city_hint": "深圳"},
    })
    print(f"Action: {result.get('action', 'unknown')}")
    print(f"Confidence: {result.get('confidence', 'unknown')}")
    print(f"Reason: {result.get('reason', '')}")


if __name__ == "__main__":
    print("SmartRoute API Examples\n")
    try:
        example_health()
        example_search_preview()
        example_route_intent()
        example_plan()
        example_adjust()
        print("\nAll examples completed successfully!")
    except urllib.error.URLError as e:
        print(f"\nError: Cannot connect to backend at {API_BASE}")
        print(f"Make sure the backend is running: python -m uvicorn api:app --port 8000")
        print(f"Details: {e}")
