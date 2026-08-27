"""SmartRoute MCP Server - Expose route planning as MCP tools for other Agent frameworks.

This module allows other AI Agent frameworks (Microsoft Agent Framework, LangGraph,
Google ADK, etc.) to call SmartRoute's route planning functionality via the MCP
(Model Context Protocol) standard interface.

Example usage from other frameworks:
    # Microsoft Agent Framework
    from microsoft.agents import Agent
    medical_agent = Agent(
        name="MedicalAgent",
        tools=[MCPTool("plan_route", server="smartroute-mcp")]
    )

    # LangGraph
    from langgraph.tools import MCPTool
    tool = MCPTool("plan_route", server_url="http://localhost:8080")
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server import Server
from mcp.types import Tool, TextContent

from api import plan_route, adjust_route
from schemas import PlanRequest, AdjustRequest


server = Server("smartroute-mcp")


@server.tool("plan_route")
async def plan_route_tool(
    query: str,
    city: str = "深圳",
    num_routes: int = 2,
    profile_source: str = "preset",
    profile_mode: str = "低排队务实型",
) -> list[TextContent]:
    """Plan routes from natural language query.

    Generate executable route options based on user's natural language description
    of their travel intentions, including time, budget, preferences, etc.

    Args:
        query: User's route planning requirement in natural language.
               Example: "深圳大学附近 3 小时路线，预算 200，不想排队"
        city: City name (default: "深圳")
        num_routes: Number of route options to generate (default: 2)
        profile_source: Profile source ("preset" or "manual_import")
        profile_mode: Profile mode for personalization (e.g., "低排队务实型")

    Returns:
        List of route options, each containing:
        - title: Route title
        - stops: List of POI stops with names, categories, duration
        - total_duration_minutes: Total route duration
        - total_cost: Estimated total cost
        - warnings: Any warnings about the route

    Example:
        plan_route("深圳大学附近 3 小时路线", "深圳", 2)
        → Returns 2 route options with POI stops, duration, and cost
    """
    request = PlanRequest(
        query=query,
        user_id="mcp-user",
        n_routes=num_routes,
        profile_source=profile_source,
        profile_mode=profile_mode,
        route_context={"city_hint": city},
    )

    try:
        result = plan_route_api(request)
        routes_data = []
        for route in result.routes:
            routes_data.append({
                "title": route.title,
                "stops": [
                    {
                        "name": stop.poi.name,
                        "category": stop.poi.category,
                        "duration_minutes": stop.stay_minutes,
                    }
                    for stop in route.stops
                ],
                "total_duration_minutes": route.total_duration_minutes,
                "total_cost": route.total_cost,
                "warnings": route.warnings,
            })
        return [TextContent(type="text", text=json.dumps(routes_data, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


@server.tool("adjust_route")
async def adjust_route_tool(
    route_id: str,
    instruction: str,
    profile_mode: str = "低排队务实型",
) -> list[TextContent]:
    """Adjust an existing route based on natural language instruction.

    Modify an existing route according to user's natural language instruction,
    such as reducing walking, lowering cost, adding stops, etc.

    Args:
        route_id: ID of the route to adjust
        instruction: Adjustment instruction in natural language.
                     Example: "少走路，便宜一点" or "加个晚餐"
        profile_mode: Profile mode for personalization

    Returns:
        Adjusted route with:
        - title: Updated route title
        - stops: Updated list of POI stops
        - adjustment_status: "applied" / "partial" / "not_applied"
        - metric_deltas: Changes in duration, cost, etc.
        - warnings: Any warnings

    Example:
        adjust_route("route-123", "少走路，便宜一点")
        → Returns adjusted route with reduced walking and lower cost
    """
    # Note: This is a simplified version. In production, you'd need to
    # retrieve the original route from storage first.
    return [TextContent(
        type="text",
        text=json.dumps({
            "status": "not_implemented",
            "message": "Route adjustment requires route storage. Use plan_route to generate new routes.",
        })
    )]


@server.tool("get_route_examples")
async def get_route_examples_tool() -> list[TextContent]:
    """Get example route planning queries for testing.

    Returns a list of example queries that users can try with the plan_route tool.

    Returns:
        List of example queries with descriptions

    Example:
        get_route_examples()
        → Returns 5 example queries for testing
    """
    examples = [
        {
            "query": "深圳大学附近 3 小时路线，预算 200，不想排队",
            "description": "经典场景：时间 + 预算 + 偏好约束",
        },
        {
            "query": "带爸妈去南山博物馆，少走路，加个咖啡",
            "description": "带长辈场景：步行约束 + 添加站点",
        },
        {
            "query": "下午 3 点开始，先去咖啡再去景点，5 点结束",
            "description": "时间窗口场景：固定时间段 + 顺序约束",
        },
        {
            "query": "外滩附近 2 小时，文艺路线，预算 300",
            "description": "跨城场景：上海地点 + 风格偏好",
        },
        {
            "query": "下雨了，换室内路线",
            "description": "天气变化场景：动态调整",
        },
    ]
    return [TextContent(type="text", text=json.dumps(examples, ensure_ascii=False))]


def run_mcp_server():
    """Run the MCP server (for standalone deployment)."""
    import asyncio
    from mcp.server.stdio import stdio_server

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream)

    asyncio.run(main())


if __name__ == "__main__":
    run_mcp_server()
