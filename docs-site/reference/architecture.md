# 架构说明

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI · Pydantic · Python 3.11+ |
| 前端 | React 19 · Vite · 高德 JS API 2.0 |
| LLM | DeepSeek |
| 地图 | 高德 Web 服务 |
| 数据 | JSON + SQLite |
| 测试 | pytest · Vitest |

## Agent 链路

```
User Query
→ IntentParserAgent（DeepSeek + 规则兜底）
→ RouteContext Resolver / AMap Adapter
→ Live Location Gate
→ AMap POI Search 或 POIRetrieverAgent
→ RoutePlannerAgent（贪心 TSP O(n²)）
→ AMap Direction Enrichment
→ RouteInsight / Explanation
→ Frontend Route UI
```

## 服务层

| 模块 | 职责 |
|------|------|
| `services/profile_service.py` | 画像管理、上下文构建 |
| `services/anchor_service.py` | 地点/锚点解析 |
| `services/route_builder.py` | 动态候选构建 |
| `services/adjustment_service.py` | 路线调整逻辑 |
| `services/trace_service.py` | Tool Trace 构建 |
| `services/route_insight.py` | 路线分析、指标、追问 |

## 架构图

详见 [`docs/images/architecture.mmd`](https://github.com/yara1006/smartroute/blob/main/docs/images/architecture.mmd)（Mermaid 格式）
