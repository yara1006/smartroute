# SmartRoute API 参考

所有接口均以 `/api` 为前缀，返回 JSON 格式。

启动后端后可访问自动生成的交互式文档：http://127.0.0.1:8000/docs

---

## 基础接口

### `GET /api/health`

返回服务健康状态。

**响应示例：**

```json
{
  "status": "ok",
  "poi_count": 500,
  "index_count": 500,
  "deepseek_enabled": true,
  "amap_enabled": true
}
```

---

### `GET /api/examples`

返回演示用 prompt 列表，供前端快速填充输入框。

---

### `GET /api/profile-sources`

返回可用画像来源（内置模拟画像、脱敏导入画像）。

**响应结构：**

```json
{
  "sources": [
    {
      "source": "preset",
      "profiles": [
        { "profile_id": "...", "display_name": "...", ... }
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

## 画像管理

### `POST /api/profile/import`

导入脱敏用户画像。后端会校验字段，拒绝包含手机号、cookie、token 等敏感信息的数据。

**请求体：**

```json
{
  "display_name": "Xiangyue 脱敏样本",
  "recent_searches": ["外滩展览", "咖啡"],
  "favorite_pois": ["seed by seed 囍得咖啡酒馆"],
  "browsed_pois": ["安静", "有设计感"],
  "favorite_categories": ["咖啡/茶饮", "景点"],
  "favorite_districts": ["黄浦区"],
  "budget_preference": 220,
  "max_wait_preference": 18,
  "walk_preference": "适中",
  "coupon_sensitive": false
}
```

**敏感字段检测：** 请求体中包含以下任意字段时直接拒绝：
`phone`、`mobile`、`password`、`cookie`、`token`、`session`、`order_id`

---

## 意图识别

### `POST /api/route-intent`

判断小团自然语言提问是否应调起 SmartRoute 插件。

**请求体：**

```json
{
  "query": "我下午要去深圳大学附近玩3个小时",
  "source": "xiaotuan",
  "context": { "city_hint": "深圳" }
}
```

**响应结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `action` | `"open_plugin"` \| `"ask_confirm"` \| `"normal_answer"` | 推荐动作 |
| `confidence` | `"high"` \| `"medium"` \| `"low"` | 置信度 |
| `reason` | `string` | 触发理由 |
| `slots` | `object` | 解析到的意图槽位 |
| `route_query` | `string` | 可传给 `/api/plan` 的规划 query |

**置信度规则：**

| 置信度 | 条件 | 动作 |
|--------|------|------|
| `high` | 地点/区域 + 时间窗口 + 串联意图 | `open_plugin` |
| `medium` | 区域 + 泛化需求，无明确串联 | `ask_confirm` |
| `low` | 单点推荐、优惠、菜品、营业时间 | `normal_answer` |

---

## 搜索预览

### `POST /api/search-preview`

搜索页入口：根据搜索词召回 4-8 个候选 POI，用户勾选后触发路线规划。

**请求体：**

```json
{
  "query": "深圳大学附近咖啡",
  "history": ["科技园咖啡"],
  "city_hint": "深圳"
}
```

**响应结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `candidates` | `POI[]` | 候选 POI 列表 |
| `default_selected_ids` | `string[]` | 默认勾选的 POI ID |
| `route_context` | `RouteContext` | 可直接传给 `/api/plan` 的上下文 |

---

## 路线规划（核心）

### `POST /api/plan`

自然语言路线规划，SmartRoute 核心接口。

**请求体：**

```json
{
  "query": "我下午要去深圳大学附近玩3个小时，帮我规划一个路线",
  "user_id": "product-demo-user",
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

**响应关键字段：**

| 字段 | 说明 |
|------|------|
| `intent` | 解析后的结构化意图（城市、时间、预算、人数等）|
| `routes` | 路线方案列表（每条含 stops、duration、cost、polyline 等）|
| `candidates` | 候选 POI 完整列表 |
| `profile_mode` | 生效的画像模式 |
| `profile_source_description` | 画像来源描述 |
| `meituan_user_context` | 美团侧用户上下文 |
| `planning_time_ms` | 规划耗时（毫秒）|
| `tool_trace` | 工具调用链路（用于前端展示 ReAct 步骤）|
| `follow_up` | 结构化追问（选项可直接触发 `/api/adjust`）|
| `route_completeness` | 路线完整性校验 |
| `constraint_conflicts` | 约束冲突说明 |
| `profile_influence` | 画像信号如何影响路线 |

---

## 路线调整

### `POST /api/adjust`

自然语言局部调整现有路线。

**请求体：**

```json
{
  "route": { "...当前路线对象..." },
  "instruction": "少走路，便宜一点",
  "profile_mode": "低排队务实型",
  "query": "我下午要去深圳大学附近玩3个小时",
  "route_context": { "..." }
}
```

**响应关键字段：**

| 字段 | 说明 |
|------|------|
| `route` | 调整后的路线 |
| `adjustment_status` | `"applied"` / `"partial"` / `"not_applied"` |
| `changed_stops` | 被修改的站点列表 |
| `before_metrics` | 调整前指标 |
| `after_metrics` | 调整后指标 |
| `metric_deltas` | 指标变化（时长、费用、等待等）|
| `adjustment_summary` | 调整说明 |
| `suggested_relaxations` | 调整失败时的放宽建议 |
| `tool_trace` | 调整步骤链路 |

---

## 同类替换

### `POST /api/replace`

替换路线中某个站点的同类 POI。

**请求体：**

```json
{
  "route": { "...当前路线对象..." },
  "stop_index": 1,
  "query": "换个咖啡馆",
  "user_id": "product-demo-user",
  "route_context": { "..." }
}
```

**响应关键字段：**

| 字段 | 说明 |
|------|------|
| `alternatives` | 同类替换候选 POI 列表 |
| `context` | 替换上下文 |
| `budget_impact` | 预算影响 |
| `wait_impact` | 等待时间影响 |
| `distance_impact` | 距离影响 |

---

## 用户反馈

### `POST /api/feedback`

将用户对路线的喜欢/不满意写入 SQLite 画像。

**请求体：**

```json
{
  "route_id": "...",
  "user_id": "product-demo-user",
  "feedback": "like",
  "stop_ids": ["poi-1", "poi-2"]
}
```

`feedback` 取值：`"like"` | `"dislike"`

---

## 错误响应

所有错误统一格式：

```json
{
  "detail": "错误描述"
}
```

常见 HTTP 状态码：

| 状态码 | 含义 |
|--------|------|
| `400` | 请求参数校验失败 / 敏感字段检测拒绝 |
| `404` | 路线/画像未找到 |
| `500` | 服务内部错误 |

---

## 相关文档

- [架构说明](ARCHITECTURE.md)
- [产品需求](PRD.md)
- [设计规范](DESIGN.md)
