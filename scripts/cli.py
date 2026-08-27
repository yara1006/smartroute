#!/usr/bin/env python3
"""SmartRoute CLI — Command-line interface for route planning and evaluation.

Provides L6 channel layer extension: CLI + Web dual entry points.

Usage:
    smartroute plan "深圳大学附近 3 小时路线"
    smartroute adjust "少走路" --route-id xxx
    smartroute eval
    smartroute health
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import typer
except ImportError:
    print("Error: typer is required. Install with: pip install typer")
    sys.exit(1)

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from api import app
from core.eval import EVAL_CASES, eval_summary, run_all_evals

# Create CLI app
cli = typer.Typer(
    name="smartroute",
    help="SmartRoute AI — Multi-agent route planning CLI",
    add_completion=False,
)


def _get_client():
    """Get FastAPI test client for CLI calls."""
    from fastapi.testclient import TestClient
    return TestClient(app)


@cli.command()
def health():
    """Check service health status."""
    client = _get_client()
    resp = client.get("/api/health")
    data = resp.json()
    print(f"Status: {data['status']}")
    print(f"POI count: {data['poi_count']}")
    print(f"Index count: {data['index_count']}")
    print(f"AMap Web Service: {data['amap_web_service']}")
    print(f"DeepSeek: {data['deepseek']}")


@cli.command()
def plan(
    query: str = typer.Argument(..., help="Natural language route planning query"),
    num_routes: int = typer.Option(2, help="Number of routes to generate"),
    profile_source: str = typer.Option("preset", help="Profile source: preset / manual_import"),
    profile_id: Optional[str] = typer.Option(None, help="Profile ID (for manual_import)"),
    city_hint: Optional[str] = typer.Option(None, help="City hint (e.g., 深圳)"),
    anchor_text: Optional[str] = typer.Option(None, help="Anchor text (e.g., 深圳大学)"),
    output: Optional[Path] = typer.Option(None, help="Save result to JSON file"),
):
    """Plan a route from natural language query.

    Example:
        smartroute plan "深圳大学附近 3 小时路线，预算 200"
        smartroute plan "外滩下午怎么玩" --city-hint 上海 --num-routes 3
    """
    client = _get_client()

    route_context = {}
    if city_hint:
        route_context["city_hint"] = city_hint
    if anchor_text:
        route_context["anchor_text"] = anchor_text

    payload = {
        "query": query,
        "user_id": "cli-user",
        "num_routes": num_routes,
        "profile_source": profile_source,
        "route_context": route_context,
    }
    if profile_id:
        payload["profile_id"] = profile_id

    start = time.time()
    resp = client.post("/api/plan", json=payload)
    elapsed_ms = int((time.time() - start) * 1000)

    if resp.status_code != 200:
        print(f"Error: {resp.json().get('detail', 'Unknown error')}")
        raise typer.Exit(code=1)

    data = resp.json()
    routes = data.get("routes", [])

    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"Planning time: {elapsed_ms}ms")
    print(f"Routes generated: {len(routes)}")
    print(f"{'='*60}\n")

    for i, route in enumerate(routes, 1):
        print(f"Route {i}: {route.get('title', 'Untitled')}")
        stops = route.get("stops", [])
        for j, stop in enumerate(stops, 1):
            poi = stop.get("poi", {})
            print(f"  {j}. {poi.get('name', 'Unknown')} ({poi.get('category', '')})")
        print(f"  Duration: {route.get('total_duration_minutes', 0)}min")
        print(f"  Cost: ¥{route.get('total_cost', 0)}")
        print()

    if output:
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"Result saved to: {output}")


@cli.command()
def adjust(
    instruction: str = typer.Argument(..., help="Natural language adjustment instruction"),
    route_id: Optional[str] = typer.Option(None, help="Route ID to adjust (uses last plan if omitted)"),
    profile_mode: str = typer.Option("低排队务实型", help="Profile mode"),
    query: str = typer.Option("", help="Original planning query"),
):
    """Adjust an existing route with natural language instruction.

    Example:
        smartroute adjust "少走路，便宜一点"
        smartroute adjust "加个晚餐" --query "深圳大学附近 3 小时"
    """
    print(f"Adjust instruction: {instruction}")
    print("(Note: CLI adjust requires a prior plan. Use 'plan' command first.)")
    print("This is a placeholder — full implementation needs session state.")


@cli.command()
def eval(
    verbose: bool = typer.Option(False, help="Show detailed results per case"),
):
    """Run all 20 eval cases and print summary.

    Example:
        smartroute eval
        smartroute eval --verbose
    """
    print(f"Running {len(EVAL_CASES)} eval cases...\n")

    # Simulate responses (in real usage, call API for each case)
    responses = {}
    for case in EVAL_CASES:
        # Placeholder: in production, call API with case.input_query
        responses[case.id] = {"query": case.input_query, "candidates": [], "routes": []}

    results = run_all_evals(responses)
    summary = eval_summary(results)

    print(f"{'Metric':<30} {'Avg':<8} {'Pass':<10} {'Total':<8} {'Pass Rate'}")
    print("-" * 70)
    for metric, stats in summary.items():
        print(
            f"{metric:<30} {stats['average']:<8.3f} {stats['passed']:<10} "
            f"{stats['total']:<8} {stats['pass_rate']:.1%}"
        )

    if verbose:
        print("\nDetailed results:")
        for r in results:
            status = "✓" if r.passed else "✗"
            print(f"  {status} {r.case_id}: {r.score}/{r.max_score} — {r.details}")


@cli.command()
def examples():
    """Show example queries for testing."""
    print("SmartRoute CLI Examples")
    print("=" * 50)
    print()
    print("1. Basic planning:")
    print('   smartroute plan "深圳大学附近 3 小时路线"')
    print()
    print("2. With constraints:")
    print('   smartroute plan "预算 200，不想排队" --city-hint 深圳 --num-routes 3')
    print()
    print("3. Health check:")
    print("   smartroute health")
    print()
    print("4. Run eval:")
    print("   smartroute eval")
    print("   smartroute eval --verbose")
    print()
    print("5. Save result:")
    print('   smartroute plan "外滩下午怎么玩" --output result.json')


if __name__ == "__main__":
    cli()
