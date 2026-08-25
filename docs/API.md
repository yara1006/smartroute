# SmartRoute AI — API Reference

> Complete HTTP API documentation for SmartRoute backend.

Base URL: `http://127.0.0.1:8000/api`

Interactive docs: `http://127.0.0.1:8000/docs`

---

## 1. Health Check

### GET /api/health

Check service health and configuration status.

**Response**:
```json
{
  "status": "ok",
  "poi_count": 500,
  "index_count": 500,
  "amap_web_service": "configured",
  "deepseek": "configured"
}
```

**Fields**:
| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Service status ("ok" or "error") |
| `poi_count` | int | Number of POIs in database |
| `index_count` | int | Number of indexed POIs |
| `amap_web_service` | string | AMap API key status |
| `deepseek` | string | DeepSeek API key status |

---

## 2. Examples

### GET /api/examples

Get example prompts for frontend demo.

**Response**:
```json
{
  "examples": [
    "我下午要去深圳大学附近玩 3 个小时，帮我规划一个路线",
    "深圳大学附近咖啡",
    ...
  ]
}
```

---

## 3. Profile Sources

### GET /api/profile-sources

Get available profile sources (built-in, imported).

**Response**:
```json
{
  "sources": [
    {
      "source": "preset",
      "profiles": [
        {"profile_id": "...", "display_name": "..."}
      ]
    },
    {
      "source": "manual_import",
      "profiles": [...]
    }
  ]
}
```

---

## 4. Profile Import

### POST /api/profile/import

Import desensitized user profile.

**Request Body**:
```json
{
  "display_name": "Xiangyue 脱敏样本",
  "recent_searches": ["外滩展览", "咖啡"],
  "favorite_pois": ["seed by seed 得咖啡酒馆"],
  "browsed_pois": ["安静", "有设计感"],
  "favorite_categories": ["咖啡/茶饮", "景点"],
  "favorite_districts": ["黄浦区"],
  "budget_preference": 220,
  "max_wait_preference": 18,
  "walk_preference": "适中",
  "coupon_sensitive": false
}
```

**Validation**:
- Rejects sensitive fields: phone, password, cookie, token, session, order_id
- Normalizes to `MeituanUserContext` format

**Response**:
```json
{
  "profile_id": "import-uuid",
  "display_name": "Xiangyue 脱敏样本",
  "signal_count": 8
}
```

---

## 5. Route Intent

### POST /api/route-intent

Determine if XiaoTuan query should trigger route planning.

**Request Body**:
```json
{
  "query": "我下午要去深圳大学附近玩 3 个小时",
  "source": "xiaotuan",
  "context": {"city_hint": "深圳"}
}
```

**Response**:
```json
{
  "action": "open_plugin",
  "confidence": "high",
  "reason": "地点 + 时间窗口 + 串联意图",
  "slots": {
    "city": "深圳",
    "duration_hours": 3,
    "anchor": "深圳大学"
  },
  "route_query": "深圳大学附近 3 小时路线"
}
```

**Confidence Levels**:
| Level | Condition | Action |
|-------|-----------|--------|
| `high` (≥0.8) | Location + time +串联 intent | `open_plugin` |
| `medium` (0.5-0.8) | Area + general need | `ask_confirm` |
| `low` (<0.5) | Single POI query | `normal_answer` |

---

## 6. Search Preview

### POST /api/search-preview

Search page entry: retrieve candidate POIs for user selection.

**Request Body**:
```json
{
  "query": "深圳大学附近咖啡",
  "history": ["科技园咖啡"],
  "city_hint": "深圳"
}
```

**Response**:
```json
{
  "candidates": [...],
  "default_selected_ids": [...],
  "route_context": {
    "source": "search",
    "city_hint": "深圳",
    "anchor_text": "深圳大学"
  }
}
```

---

## 7. Plan Route (Core)

### POST /api/plan

Plan routes from natural language query. **Core endpoint**.

**Request Body**:
```json
{
  "query": "我下午要去深圳大学附近玩 3 个小时，帮我规划一个路线",
  "user_id": "demo-user",
  "num_routes": 2,
  "profile_source": "preset",
  "profile_id": "low-wait-pragmatic",
  "route_context": {
    "source": "search",
    "city_hint": "深圳",
    "anchor_text": "深圳大学",
    "selected_pois": [],
    "transport_strategy": "步行优先",
    "fixed_start_poi_id": null,
    "pinned_policy": null
  }
}
```

**Response**:
```json
{
  "user_id": "demo-user",
  "query": "...",
  "intent": {
    "city": "深圳",
    "duration_hours": 3,
    "budget": null,
    "parser_source": "deepseek",
    "parser_confidence": 0.92
  },
  "profile": {...},
  "profile_mode": "低排队务实型",
  "profile_source": "preset",
  "profile_source_description": "模拟画像 · 低排队务实型",
  "profile_signal_count": 5,
  "meituan_user_context": {...},
  "candidates": [...],
  "routes": [
    {
      "title": "科技 + 咖啡半日游",
      "description": "...",
      "stops": [...],
      "total_duration_minutes": 180,
      "total_cost": 185,
      "map_polyline": [...],
      "transit_segments": [...]
    }
  ],
  "trace": [...],
  "planning_time_ms": 234,
  "follow_up_question": "需要加个晚餐吗？",
  "follow_up": {
    "question": "需要加个晚餐吗？",
    "options": [...]
  },
  "profile_influence": [...],
  "constraint_conflicts": [],
  "route_completeness": {
    "has_food": true,
    "has_entertainment": true,
    "min_stops": 3,
    "complete": true
  },
  "tool_trace": [
    {"tool": "IntentParser", "source": "deepseek", "duration_ms": 120},
    {"tool": "AMapSearch", "query": "深圳大学", "results": 8}
  ],
  "safety_warnings": [],
  "refused": false
}
```

**Key Fields**:
| Field | Type | Description |
|-------|------|-------------|
| `intent` | object | Parsed intent slots |
| `routes` | array | Generated route options |
| `planning_time_ms` | int | Planning duration |
| `tool_trace` | array | Tool invocation trace |
| `profile_influence` | array | How profile affected routing |
| `route_completeness` | object | Validation results |
| `safety_warnings` | array | Safety intercept messages |
| `refused` | boolean | True if high-risk action blocked |

---

## 8. Adjust Route

### POST /api/adjust

Adjust existing route with natural language instruction.

**Request Body**:
```json
{
  "route": {...},
  "instruction": "少走路，便宜一点",
  "profile_mode": "低排队务实型",
  "query": "深圳大学附近 3 小时路线",
  "route_context": {...}
}
```

**Response**:
```json
{
  "route": {...},
  "adjustment_status": "applied",
  "changed_stops": [
    {"index": 2, "old_poi": "...", "new_poi": "..."}
  ],
  "before_metrics": {
    "total_duration_minutes": 180,
    "total_cost": 185
  },
  "after_metrics": {
    "total_duration_minutes": 150,
    "total_cost": 120
  },
  "metric_deltas": {
    "duration_minutes": -30,
    "total_cost": -65
  },
  "adjustment_summary": "已替换 2 个站点，减少步行距离",
  "suggested_relaxations": [],
  "tool_trace": [...],
  "safety_warnings": [],
  "refused": false
}
```

**Adjustment Status**:
| Status | Meaning |
|--------|---------|
| `applied` | All changes applied |
| `partial` | Some changes applied |
| `not_applied` | No changes possible |

---

## 9. Replace POI

### POST /api/replace

Replace a route stop with similar POI.

**Request Body**:
```json
{
  "route": {...},
  "stop_index": 1,
  "query": "换个咖啡馆",
  "user_id": "demo-user",
  "route_context": {...}
}
```

**Response**:
```json
{
  "alternatives": [...],
  "context": {...},
  "budget_impact": -20,
  "wait_impact": -5,
  "distance_impact": 200
}
```

---

## 10. Feedback

### POST /api/feedback

Record user feedback on route (like/dislike).

**Request Body**:
```json
{
  "route_id": "...",
  "user_id": "demo-user",
  "feedback": "like",
  "stop_ids": ["poi-1", "poi-2"]
}
```

**Response**:
```json
{
  "status": "ok",
  "message": "反馈已记录"
}
```

---

## Error Responses

All errors return:
```json
{
  "detail": "错误描述"
}
```

**Common Status Codes**:
| Code | Meaning |
|------|---------|
| 400 | Validation failed / sensitive field detected |
| 401 | Authentication required |
| 404 | Route/profile not found |
| 429 | Rate limited |
| 500 | Internal server error |
| 503 | External service unavailable (DeepSeek/AMap) |

---

## Rate Limiting

- Default: 60 requests/minute per IP
- Configurable via environment variables

---

**Last updated**: 2026-08-25
