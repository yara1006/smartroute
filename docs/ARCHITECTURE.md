# SmartRoute Architecture

## 1. 当前技术栈

前端：

- React 19
- Vite
- 高德 JS API 2.0
- `@amap/amap-jsapi-loader`
- 高德 Web 服务：地理编码、周边 POI、路径规划

后端：

- FastAPI
- Pydantic
- Python 3.14

数据与存储：

- 本地 POI JSON：`data/pois.json`
- 本地 UGC JSON：`data/ugc_reviews.json`
- 本地轻量索引：`data/local_index/poi_index.json`
- 用户画像 SQLite：`data/user_profiles.db`

旧版原型：

- Streamlit 原型仍保留，用于早期链路验证。

## 2. 核心 Agent 链路

当前链路：

```text
User Query
→ IntentParserAgent
→ RouteContext Resolver / AMap Adapter
→ POIRetrieverAgent or AMap POI Search
→ RoutePlannerAgent
→ AMap Direction Enrichment
→ RouteInsight / Explanation
→ UserProfileManager
→ Frontend Route UI
```

小团入口链路：

```text
XiaoTuan Query
→ RouteIntentRouterAgent
→ route intent? yes / maybe / no
→ SmartRoute Plugin Card
→ IntentParserAgent
→ POIRetrieverAgent
→ RoutePlannerAgent
→ RouteInsight / Explanation
→ UserProfileManager
→ Frontend Route UI
```

模块职责：

- `RouteIntentRouterAgent`：判断小团通用提问是否应该调起 SmartRoute，优先 DeepSeek，失败或无 Key 时规则兜底，输出置信度、触发理由和建议动作。
- `IntentParserAgent`：解析自然语言中的城市、时间、预算、人数、等待、区域、类别和风格。
- `POIRetrieverAgent`：根据约束和用户画像，从本地索引召回候选 POI。
- `AMapClient`：使用 `AMAP_WEB_SERVICE_KEY` 调用高德 Web 服务，把“深圳大学/外滩/当前店铺”解析为锚点，召回周边 POI，并补充真实道路 polyline；无 Key 或失败时返回非阻断降级。
- `RoutePlannerAgent`：生成紧凑、高分、低等待等路线变体。
- `UserProfileManager`：读取和写入 SQLite 用户画像，沉淀喜欢/不合适反馈。
- `route_insight`：生成可信度、约束命中、预算剩余、步行强度、人群适配和风险解释。

`RouteIntentRouterAgent` 判定规则：

- 高置信：用户同时表达地点/区域、时间窗口、串联/安排意图，或明确说“路线”“规划”“半天怎么玩”“吃完再逛”。
- 中置信：用户表达区域和泛化需求，但没有明确要求串联，例如“外滩下午有什么好玩的”。
- 低置信：用户只问单点推荐、优惠、菜品、营业时间、电话、地址等，不调起 SmartRoute。
- 高置信直接调起插件；中置信返回确认卡；低置信保持小团普通回答，仅保留次级“排成路线”入口。

## 3. 数据模型

核心模型：

- `POI`：名称、类别、地址、区域、经纬度、评分、人均、等待、营业时间、标签、UGC 摘要。
- `UserConstraints`：城市、起点、时间、预算、等待、步行、人数、交通方式、偏好类别、偏好区域。
- `RouteStop`：站点顺序、POI、到达时间、离开时间、停留时长、等待、到下一站交通。
- `Route`：路线标题、描述、站点列表、总时长、人均、等待、交通、亮点、风险。
- `UserProfile`：偏好类别、不喜欢类别、预算、时间段、风格、访问/喜欢/不喜欢 POI。
- `MeituanUserContext`：模拟美团侧搜索偏好、收藏品类、浏览标签、常用预算、常去商圈、排队容忍度、步行偏好、优惠敏感度，用于路线召回和排序加权。
- `ManualProfileImportRequest`：脱敏画像导入结构，支持搜索词、收藏 POI、浏览偏好、常用区域、预算、排队、步行和优惠敏感度。
- `ProfileSourceView` / `ImportedProfileView`：描述可用画像来源，区分 `preset`、`manual_import` 和预留的 `official_api`。
- `ProfileInfluence`：解释画像信号如何影响召回加权和路线选择。
- `FollowUp` / `FollowUpOption`：结构化追问卡，选项可直接映射为 `/api/adjust` 指令。
- `RouteMetrics` / `MetricDeltas`：记录调整前后总时长、人均、等待、交通和站点数变化。
- `ChangedStop`：记录局部调整替换、重排或新增了哪些站点。
- `RouteContext`：前端入口上下文，包含 `source`、`city_hint`、`anchor_text`、`anchor_location`、`selected_pois`。
- `POI.source / external_id / distance_from_anchor_meters`：标记 POI 来自高德、入口已选或本地兜底。
- `Route.map_polyline / transit_segments`：承载高德路径规划或本地估算路径，前端优先按 polyline 绘制。

## 4. 当前 API

`GET /api/health`

- 返回服务状态、POI 数量、索引数量。

`GET /api/examples`

- 返回演示用 prompt。

`GET /api/profile-sources`

- 返回可用画像来源：内置模拟画像、脱敏导入画像、未启用的官方授权 API。
- 默认提供两个脱敏样本占位，方便演示“不同真实样本路线不同”。

`POST /api/profile/import`

- 输入用户手动整理后的脱敏画像 JSON。
- 保存到本地 `data/profile_imports.json`，并归一化为 `MeituanUserContext`。
- 如果包含手机号、账号、cookie、token、订单号等敏感字段，直接拒绝。

`POST /api/route-intent`

- 输入小团自然语言 query、入口 source 和上下文 context。
- 返回 `open_plugin`、`ask_confirm` 或 `normal_answer`，以及置信度、触发理由、识别槽位和 SmartRoute 规划 query。
- 优先使用 DeepSeek；无 Key、超时或返回不合法时使用规则兜底。

`POST /api/plan`

- 输入自然语言 query、user_id、路线数量、`profile_source`、可选 `profile_id`，以及可选 `route_context`。
- `route_context` 支持搜索/小团的地点锚点、收藏夹已选 POI、POI 详情页当前商户坐标。
- 返回解析意图、用户画像、画像来源、模拟/脱敏画像上下文、候选 POI、路线方案、生成 trace、规划耗时、画像影响、冲突解释、路线完整性和结构化生成后追问。

`POST /api/adjust`

- 输入当前路线、自然语言调整指令、用户画像模式、原始 query。
- 返回调整后的路线、调整状态、被修改的站点、调整前后指标、指标变化、调整说明、失败放宽建议、冲突解释、规划耗时和下一步追问。
- 当前为规则版局部调整，覆盖少走路、便宜点、不要排队、加晚餐/咖啡/展览。

`POST /api/replace`

- 输入当前路线、需要替换的站点序号、query、user_id。
- 返回同类可替换 POI 和预算/等待/距离影响。

`POST /api/feedback`

- 输入 route 和 feedback。
- 将喜欢/不合适写入 SQLite 用户画像。

## 5. P1 状态字段

- `planning_time_ms`：规划耗时。
- `constraint_conflicts`：冲突说明。
- `profile_mode`：演示画像模式，例如低排队、文艺、带爸妈。
- `profile_source`：画像来源，当前支持 `preset` 和 `manual_import`；`official_api` 预留但默认禁用。
- `profile_id`：脱敏导入画像 ID。
- `profile_source_description`：面向前端展示的画像来源说明，例如“脱敏导入 · Xiangyue 样本 · 18 个信号”。
- `profile_signal_count`：画像信号数量，用于解释真实感和数据密度。
- `meituan_user_context`：美团侧搜索、收藏、浏览、到店和预算偏好摘要。
- `follow_up_question`：路线生成后用于提升满意度的追问。
- `follow_up`：结构化追问，包含问题、选项和每个选项对应的调整指令。
- `route_completeness`：路线完整性校验结果。
- `profile_influence`：画像信号、来源、加权影响和命中的 POI。
- `adjustment_status`：`applied / partial / not_applied`，避免无法改善时假装成功。
- `before_metrics` / `after_metrics` / `metric_deltas`：局部调整前后的指标变化。
- `changed_stops`：替换、重排或新增的站点说明。
- `suggested_relaxations`：调整失败或只部分成功时的放宽建议。

## 6. 与通用大模型的关系

DeepSeek、豆包、OpenAI 等通用模型适合做：

- 自然语言理解。
- 多轮对话。
- 调整意图解析。
- 解释生成。

但它们不能替代：

- 美团 POI 数据。
- UGC 和用户评价。
- 价格、排队、营业时间。
- 用户画像和历史反馈。
- 交易、订座、领券、打车、导航等履约工具。
- 可执行路线约束求解。

因此架构上，大模型应作为 Agent 推理层，SmartRoute 的核心价值在于“LLM + 美团数据 + 搜索/规划工具 + 用户记忆 + 履约闭环”。

## 7. 开发约束

- 不在前端硬编码路线结果。
- 不提交 `web/.env.local`、高德 Key 或其他密钥。
- 不破坏现有 `POI`、`Route`、`UserConstraints` 模型。
- 新增能力优先通过 API 扩展，而不是只改前端展示。
- 每条主路线需要稳定满足 >=3 POI。
- 每条主路线需要强制覆盖餐饮 + 文化/娱乐。
- 调整路线时必须保留当前路线上下文，避免表现为“重新开始”。

## 8. 当前风险

- 当前 `/api/adjust` 是规则版局部调整，还不是 DeepSeek Function Calling / ToolUse。
- 当前画像支持模拟画像和脱敏手动导入画像，不是真实美团官方账号授权数据。
- 高德 Web 服务 Key 缺失或域名/额度限制时，会降级为锚点附近本地候选和估算路径；不会让 Demo 白屏。
- 不允许通过自动登录、抓 cookie 或爬取个人账号方式获取真实画像。
