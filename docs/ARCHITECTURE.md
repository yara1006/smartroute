# SmartRoute Architecture

## 1. 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI · Pydantic · Python 3.11+ |
| 前端框架 | React 19 · Vite · 高德 JS API 2.0 |
| LLM | DeepSeek（意图解析 + 调整工具选择）|
| 地图服务 | 高德 Web 服务（POI 搜索、地理编码、路径规划）|
| 本地数据 | `data/pois.json` · `data/ugc_reviews.json` |
| 向量索引 | `data/local_index/poi_index.json` |
| 用户画像 | SQLite：`data/user_profiles.db` |
| 测试 | pytest · 200 测试 · Vitest |
| 部署 | Docker · docker-compose · GitHub Actions |

## 2. 目录结构

```
smartroute/
├── api.py                    # FastAPI 路由层（~800 行）
├── schemas.py                # 所有 Pydantic 请求/响应模型
├── core/
│   ├── config.py             # 集中配置（Settings 单例）
│   ├── logging_config.py     # 结构化日志
│   ├── models.py             # 核心数据模型（POI、Route 等）
│   ├── agents/               # Multi-Agent 系统
│   │   ├── route_intent_router.py  # 小团入口意图路由
│   │   ├── intent_parser.py        # 自然语言意图解析
│   │   ├── poi_retriever.py        # POI 检索 Agent
│   │   └── route_planner.py        # 路线规划（TSP 贪心优化）
│   ├── services/
│   │   └── amap_client.py    # 高德 Web 服务客户端（TTL 缓存）
│   ├── rag/
│   │   └── vector_store.py   # 本地向量检索（中文 bigram）
│   └── memory/
│       └── user_profile.py   # SQLite 画像读写
├── services/                 # 业务逻辑服务层
│   ├── route_service.py      # 统一 re-export facade
│   ├── profile_service.py    # 画像管理与上下文构建
│   ├── anchor_service.py     # 地点/锚点解析
│   ├── route_builder.py      # 动态候选构建
│   ├── adjustment_service.py # 路线调整逻辑
│   ├── trace_service.py      # Tool trace 构建
│   └── route_insight.py      # 路线分析、指标、追问
├── web/                      # React 前端
│   └── src/
│       ├── App.jsx           # 主应用（~610 行）
│       ├── components/       # UI 组件
│       │   ├── Panels.jsx
│       │   ├── PhoneExperience.jsx
│       │   ├── RouteMap.jsx
│       │   ├── QueryComposer.jsx
│       │   └── ErrorBoundary.jsx
│       ├── api.js            # API 请求封装
│       ├── helpers.js        # 工具函数
│       └── constants.js      # 常量定义
├── tests/                    # pytest 后端测试
├── .github/workflows/        # CI/CD
└── docs/                     # 项目文档
```

## 3. 核心 Agent 链路

### 主链路

```text
User Query
→ IntentParserAgent（DeepSeek LLM + 规则兜底）
→ RouteContext Resolver / AMap Adapter
→ Live Location Gate（真实地点 / 本地兜底）
→ AMap POI Search 或 POIRetrieverAgent
→ RoutePlannerAgent（贪心 TSP 优化）
→ AMap Direction Enrichment
→ RouteInsight / Explanation
→ UserProfileManager
→ Frontend Route UI
```

### 小团入口链路

```text
XiaoTuan Query
→ RouteIntentRouterAgent（意图置信度分流）
  → 高置信 → SmartRoute Plugin Card
  → 中置信 → 确认卡（保留"排成路线"入口）
  → 低置信 → 小团普通回答
→ IntentParserAgent
→ POIRetrieverAgent / AMap POI Search
→ RoutePlannerAgent
→ RouteInsight / Explanation
→ UserProfileManager
→ Frontend Route UI
```

### Agent 职责

| Agent | 职责 |
|-------|------|
| `RouteIntentRouterAgent` | 判断小团提问是否应调起 SmartRoute；DeepSeek 优先，规则兜底 |
| `IntentParserAgent` | 解析自然语言中的城市、时间、预算、人数、等待、区域、类别偏好 |
| `POIRetrieverAgent` | 无明确地点时从本地索引召回候选 POI |
| `RoutePlannerAgent` | 生成多条差异化路线，O(n²) 贪心 TSP 优化 |
| `AMapClient` | 调用高德 Web 服务，30 分钟 TTL 缓存，错误日志记录 |

## 4. 服务层模块

业务逻辑拆分为 6 个独立服务模块，通过 `services/route_service.py` 作为向后兼容的 re-export facade 统一导出。

### `services/profile_service.py`

- 画像上下文构建：`resolve_profile_context`、`profile_with_context`、`intent_with_context`
- 画像导入导出：`validate_import_payload`、`imported_record_to_context`
- 导入记录管理：`load_imported_profile_records`

### `services/anchor_service.py`

- 锚点解析：`extract_anchor_text`、`resolve_route_anchor`
- 城市推断：`city_hint_from`
- 类别/角色辅助：`categories_for_live_route`、`unique_categories`、`route_role_keywords`
- 实时位置判断：`requires_live_location_data`

### `services/route_builder.py`

- 候选构建：`build_dynamic_candidates`
- 高德路径分段：`enrich_route_with_amap_segments`
- 画像上下文应用：`apply_context_to_candidates`

### `services/adjustment_service.py`

- 调整意图解析：`parse_adjustment_intent`、`detect_adjustment_kind`
- 目标候选查找：`find_adjustment_candidate`、`choose_adjustment_target`
- 状态评估：`adjustment_status_for`、`suggested_relaxations_for`

### `services/trace_service.py`

- 工具链路构建：`trace_step`、`build_plan_tool_trace`、`build_trace`
- LLM 分类：`classify_adjustment_with_deepseek`

### `services/route_insight.py`

- 路线分析：`route_insight`、`route_metrics`、`metric_deltas`
- 完整性校验：`build_route_completeness`、`build_constraint_conflicts`
- 追问构建：`build_follow_up`、`build_profile_influence`

## 5. 集中配置

`core/config.py` 提供 `Settings` 单例，统一管理所有环境变量和路径：

```python
from core.config import get_settings

settings = get_settings()
settings.deepseek_enabled   # 是否配置 DeepSeek Key
settings.amap_enabled       # 是否配置高德 Web 服务 Key
settings.cors_origins       # CORS 允许的来源（从 CORS_ORIGINS 环境变量读取）
```

所有路径（`DATA_DIR`、`POI_PATH`、`INDEX_DIR` 等）均在 `core/config.py` 定义，其他模块从此处导入，不再各自维护。

## 6. 数据模型

| 模型 | 说明 |
|------|------|
| `POI` | 名称、类别、地址、经纬度、评分、人均、等待、标签、UGC 摘要 |
| `UserConstraints` | 城市、起点、时间、预算、等待、步行、人数、交通、偏好 |
| `Route` | 路线标题、描述、站点列表、总时长、polyline、transit_segments |
| `RouteStop` | 站点顺序、POI、到达/离开时间、等待、到下一站交通 |
| `UserProfile` | 偏好类别、不喜欢类别、预算、时间段、风格 |
| `MeituanUserContext` | 搜索偏好、收藏品类、浏览标签、预算、排队、步行偏好 |
| `RouteContext` | 入口上下文：source、city_hint、anchor_text、selected_pois、transport_strategy |
| `AgentTraceStep` | 工具名、输入摘要、输出摘要、状态（用于 Tool Trace 展示）|
| `RouteMetrics` / `MetricDeltas` | 调整前后的指标变化 |

## 7. API 概览

| 端点 | 说明 |
|------|------|
| `GET /api/health` | 服务状态、POI 数量 |
| `GET /api/examples` | 演示用 prompt |
| `GET /api/profile-sources` | 可用画像来源 |
| `POST /api/profile/import` | 脱敏画像导入 |
| `POST /api/route-intent` | 小团意图识别 |
| `POST /api/search-preview` | 搜索页候选 POI |
| `POST /api/plan` | 路线规划（核心接口）|
| `POST /api/adjust` | 自然语言路线调整 |
| `POST /api/replace` | 同类 POI 替换 |
| `POST /api/feedback` | 用户反馈写入画像 |

详见 [API 文档](API.md)。

## 8. 开发约束

- 不在前端硬编码路线结果
- 不提交 `.env`、`web/.env.local`、高德 Key 或其他密钥
- 明确地点/城市/坐标的请求必须走高德 Web 服务或入口已选 POI，禁止静默跨城回退
- 每条主路线稳定满足 ≥3 POI，且强制覆盖餐饮 + 文化/娱乐
- 调整路线时必须保留当前路线上下文
- 新增能力优先通过 API 扩展，而不是只改前端展示

## 9. 已知风险

| 风险 | 应对 |
|------|------|
| DeepSeek Key 未配置或额度不足 | 自动降级为规则兜底，`parser_source=fallback` |
| 高德 Key 类型错误（JS API 填入 Web 服务）| 返回 `USERKEY_PLAT_NOMATCH`，提示配置错误 |
| 无真实美团账号授权 | 支持模拟画像 + 脱敏导入，预留 `official_api` adapter |
| 高德 QPS 限制 | 30 分钟 TTL 缓存，降低演示重复调用风险 |
