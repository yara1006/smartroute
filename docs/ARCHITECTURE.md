# SmartRoute AI — Architecture Document

> Multi-agent route planning system for Meituan AI Hackathon.

## 1. System Overview

SmartRoute AI is a local-life route planning agent that converts natural language travel intentions into executable itineraries. It integrates with AMap (高德) Web Service for real POI data, uses DeepSeek LLM for intent parsing, and supports user profile-driven personalization.

### Key Features

- **Natural Language Intent Parsing**: DeepSeek LLM with rules fallback
- **Multi-Entry Point**: Search, XiaoTuan chat, Favorites, POI detail page
- **User Profile Personalization**: 3 built-in profiles + desensitized import + judge session
- **Real Location Planning**: AMap Web Service with cross-city protection
- **Route Adjustment**: Natural language modifications with Tool Trace
- **Safety Boundaries**: Intercepts 5 high-risk action types

---

## 2. System Architecture

```
─────────────────────────────────────────────────────────────┐
│                        ENTRY POINTS                          │
│  ┌─────────┐  ──────────┐  ┌─────────┐  ┌─────────────┐  │
│  │ Search  │  │XiaoTuan  │  │Favorites│  │POI Detail   │  │
│  │  搜索页  │  │  问小团   │  │  收藏夹  │  │  POI 详情页  │  │
│  └─────────  └──────────┘  └─────────┘  └─────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                      API LAYER (FastAPI)                     │
│  /api/plan · /api/adjust · /api/search-preview · /api/...   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    AGENT SYSTEM (4 Agents)                   │
│  ┌─────────────────┐  ┌─────────────────────────────────┐  │
│  │RouteIntentRouter│→│ IntentParser (DeepSeek + Rules)  │  │
│  │  意图置信度分流  │  │        意图解析 + 规则兜底         │  │
│  ─────────────────┘  └─────────────────────────────────┘  │
│  ┌─────────────────┐  ┌─────────────────────────────────┐  │
│  │ POIRetriever    │→│    RoutePlanner (Greedy TSP)     │  │
│  │   本地向量检索   │  │      贪心最近邻 O(n²)             │  │
│  └─────────────────┘  └─────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  BUSINESS SERVICES (6 modules)               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │profile_svc   │  │anchor_svc    │  │route_builder     │  │
│  │  画像管理     │  │  地点解析     │  │   动态路线构建    │  │
│  └──────────────┘  └──────────────  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │adjustment_svc│  │trace_svc     │  │route_insight     │  │
│  │  路线调整     │  │  Tool Trace  │  │  路线分析/指标     │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└────────────────────┬────────────────────────────────────────
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │SQLite        │  │POI Vector    │  │DeepSeek API      │  │
│  │用户画像       │  │本地向量索引   │  │意图解析/调整工具   │  │
│  ──────────────┘  └──────────────┘  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │AMap Web Svc  │  │Settings      │                        │
│  │POI/路径/编码  │  │集中配置       │                        │
│  └──────────────┘  └──────────────                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Multi-Agent Pipeline

### 3.1 RouteIntentRouter Agent
**Purpose**: Determine if a XiaoTuan query should trigger route planning.

**Confidence Levels**:
- **High** (≥0.8): Direct plugin activation
- **Medium** (0.5-0.8): Show confirmation card
- **Low** (<0.5): Normal XiaoTuan response

**Implementation**: `core/agents/route_intent_router.py`

### 3.2 IntentParser Agent
**Purpose**: Parse natural language into structured slots (city, time, budget, party size, preferences).

**Dual Mode**:
- **LLM Mode**: DeepSeek API with structured output
- **Rules Fallback**: Keyword/pattern matching when API unavailable

**Implementation**: `core/agents/intent_parser.py`

### 3.3 POIRetriever Agent
**Purpose**: Retrieve candidate POIs based on constraints and user profile.

**Sources**:
- Local vector store (Chinese bigram tokenization)
- AMap Web Service (when location anchor present)

**Implementation**: `core/agents/poi_retriever.py`

### 3.4 RoutePlanner Agent
**Purpose**: Generate differentiated route options with TSP optimization.

**Algorithm**: Greedy nearest-neighbor O(n²) instead of O(n!) permutations.

**Implementation**: `core/agents/route_planner.py`

---

## 4. Service Layer

### 4.1 profile_service.py
- Profile context building
- Profile import/export validation
- Imported record to context conversion

### 4.2 anchor_service.py
- Location/anchor text extraction
- City hint detection
- Route anchor resolution
- Live location data requirement check

### 4.3 route_builder.py
- Dynamic candidate building
- AMap segment enrichment
- Profile context application to candidates

### 4.4 adjustment_service.py
- Adjustment intent parsing
- Candidate search for adjustments
- Adjustment status evaluation
- Category detection (add/remove/change)

### 4.5 trace_service.py
- Tool trace step recording
- Plan trace building
- DeepSeek classification for adjustments

### 4.6 route_insight.py
- Route completeness validation
- Constraint conflict detection
- Route metrics calculation
- Follow-up question generation

---

## 5. Key Design Decisions

### 5.1 LLM Priority + Rules Fallback
**Why**: Demo must work without API key; rules provide baseline functionality.

**Trade-off**: Rules accuracy ~70% vs LLM ~90%+, but rules guarantee demo never fails.

### 5.2 Greedy TSP vs Exact Solution
**Why**: O(n!) permutations unacceptable for >6 stops; greedy O(n²) quality loss <5% for ≤10 stops.

**Trade-off**: Not globally optimal, but fast enough for real-time planning.

### 5.3 Cross-City Protection
**Why**: Prevent silent fallback to wrong city's local RAG when AMap fails.

**Implementation**: Explicit location anchor required; failure returns clear error trace.

### 5.4 Service Layer Split
**Why**: Original `api.py` was 2868 lines; split into 6 focused modules for testability.

**Trade-off**: Cross-module imports require explicit dependencies; `route_service.py` facade maintains backward compatibility.

---

## 6. Data Models

### POI
```python
class POI(BaseModel):
    id: str
    name: str
    category: POICategory
    address: str
    district: str
    latitude: float
    longitude: float
    rating: float
    price_per_person: float
    avg_wait_minutes: int
    business_hours: dict[str, str]
    tags: list[str]
    source: str  # "amap" | "seed" | "context"
    price_range: list[float] | None  # [min, max] estimated
    is_estimated: bool  # True when data from estimates
```

### Route
```python
class Route(BaseModel):
    title: str
    description: str
    stops: list[RouteStop]
    total_duration_minutes: int
    total_cost: float
    map_polyline: list
```

### RouteContext
```python
class RouteContext(BaseModel):
    source: str  # "search" | "xiaotuan" | "favorites" | "detail"
    city_hint: str | None
    anchor_text: str | None
    anchor_location: dict | None
    selected_pois: list[POI]
    transport_strategy: str | None
    fixed_start_poi_id: str | None
    pinned_policy: str | None
```

---

## 7. Safety Boundaries

### High-Risk Actions (Intercepted)
1. **Booking**: "帮我预订" → Refuse, suggest official platform
2. **Payment**: "帮我付款" → Refuse
3. **Save Credentials**: "记住我的身份证/银行卡" → Refuse
4. **Non-Refundable**: "订不可退款的酒店" → Warn about terms
5. **Legal Confirmation**: "帮我确认签证" → Suggest official channels

**Implementation**: `services/safety_reviewer.py`

---

## 8. Testing & Evaluation

### Test Coverage
- **Backend**: 200+ tests, 83% coverage (threshold 80%)
- **Frontend**: 48 tests (Vitest)
- **Total**: 248+ tests

### Eval Framework (20 cases × 5 metrics)
| Metric | Description |
|--------|-------------|
| `constraint_satisfaction` | Budget, time, preference satisfaction |
| `route_reasonableness` | Route quality, no backtracking |
| `source_grounding` | External data has source/date |
| `uncertainty_disclosure` | Prices/hours marked as estimated |
| `safety_compliance` | High-risk actions intercepted |

**Implementation**: `core/eval/eval_cases.py`

---

## 9. Deployment

### Docker
```bash
docker-compose up -d
```

### GitHub Actions CI
- Lint: ruff + mypy
- Test: Python 3.11/3.12/3.13 matrix
- Frontend: npm test + build
- Coverage: ≥80% required

### VitePress Documentation Site
- Guide: Getting started, configuration, deployment
- Reference: API, architecture, data models

---

## 10. File Structure

```
smartroute/
├── api.py                    # FastAPI route handlers (~800 lines)
├── schemas.py                # Pydantic models (290 lines)
── cli.py                    # CLI entry (typer)
├── core/
│   ├── config.py             # Settings singleton
│   ├── models.py             # Core data models
│   ├── agents/               # 4 agents
│   ├── services/             # AMap client
│   ├── rag/                  # Vector store
│   ├── memory/               # User profiles
│   └── eval/                 # Eval framework
├── services/                 # 6 business modules
│   ├── route_service.py      # Re-export facade
│   ├── profile_service.py
│   ├── anchor_service.py
│   ├── route_builder.py
│   ├── adjustment_service.py
│   ├── trace_service.py
│   ├── safety_reviewer.py
│   └── route_insight.py
├── web/                      # React frontend
├── tests/                    # Backend tests (200+)
── docs-site/                # VitePress docs
└── docs/
    ├── ARCHITECTURE.md       # This file
    ├── API.md
    ├── RETROSPECTIVE.md
    └── images/
```

---

**Last updated**: 2026-08-25
