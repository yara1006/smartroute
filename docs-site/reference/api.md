# API 接口参考

所有接口均以 `/api` 为前缀，返回 JSON 格式。

启动后端后访问自动生成的交互式文档：http://127.0.0.1:8000/docs

## 基础接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 服务健康状态 |
| GET | `/api/examples` | 演示 prompt 列表 |
| GET | `/api/profile-sources` | 可用画像来源 |

## 核心接口

### `POST /api/plan` — 路线规划

SmartRoute 核心接口，自然语言生成路线。

**请求体：**

```json
{
  "query": "我下午要去深圳大学附近玩3个小时",
  "user_id": "demo-user",
  "num_routes": 2,
  "profile_source": "preset",
  "profile_id": "low-wait-pragmatic",
  "route_context": {
    "source": "search",
    "city_hint": "深圳",
    "anchor_text": "深圳大学"
  }
}
```

**响应关键字段：**

| 字段 | 说明 |
|------|------|
| `intent` | 结构化意图（城市、时间、预算等）|
| `routes` | 路线方案列表 |
| `tool_trace` | 工具调用链路 |
| `follow_up` | 结构化追问 |
| `profile_influence` | 画像信号影响说明 |

### `POST /api/adjust` — 路线调整

自然语言局部调整现有路线。

**请求体：**

```json
{
  "route": { "..." },
  "instruction": "少走路，便宜一点",
  "profile_mode": "低排队务实型",
  "query": "原始 query"
}
```

**响应关键字段：**

| 字段 | 说明 |
|------|------|
| `route` | 调整后的路线 |
| `adjustment_status` | `applied` / `partial` / `not_applied` |
| `metric_deltas` | 指标变化 |
| `suggested_relaxations` | 失败时的放宽建议 |

### `POST /api/search-preview` — 搜索候选

根据搜索词召回候选 POI，用户勾选后触发规划。

### `POST /api/route-intent` — 意图识别

判断小团提问是否应调起 SmartRoute 插件。

### `POST /api/replace` — 同类替换

替换路线中某个站点的同类 POI。

### `POST /api/feedback` — 用户反馈

将喜欢/不满意写入 SQLite 画像。
