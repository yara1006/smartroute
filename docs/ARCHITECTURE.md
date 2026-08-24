# SmartRoute Architecture

## 1. 当前技术栈

前端：

- React 19
- Vite
- 高德 JS API 2.0
- `@amap/amap-jsapi-loader`
- 高德 Web 服务：POI 文本搜索、地理编码、周边 POI、路径规划

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
→ IntentParserAgent (DeepSeek LLM + rules fallback)
→ RouteContext Resolver / AMap Adapter
→ Live Location Gate
→ AMap POI Search or POIRetrieverAgent
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
- `IntentParserAgent`：解析自然语言中的城市、时间、预算、人数、等待、区域、类别和风格；配置 DeepSeek Key 后优先用 LLM 输出结构化槽位，无 Key 或失败时规则兜底。
- `ToolUse Adjustment Chain`：`/api/adjust` 以 ReAct / ToolUse 风格组织 Parse adjustment、Search replacement POI、Validate constraints、Update route、Explain changes，并返回 `tool_trace` 给前端展示。
- `Live Location Gate`：判断请求是否包含明确城市、地标、商圈、入口坐标或已选 POI。命中后进入真实地点模式，禁止跨城回退到本地 RAG。
- `POIRetrieverAgent`：根据约束和用户画像，从本地索引召回候选 POI；仅用于无明确地点的通用演示或本地兜底，不覆盖真实地点模式。
- `AMapClient`：使用 `AMAP_WEB_SERVICE_KEY` 调用高德 Web 服务，优先用 POI 文本搜索把“广州永庆坊/北京金鱼胡同/中山大学/深圳大学/三里屯/外滩/当前店铺”解析为真实锚点，地理编码作为兜底；随后召回周边 POI，并补充真实道路 polyline。适配器会记录最近错误，便于排查 Key 类型、权限、额度或网络问题，并对同路径同参数请求做 30 分钟内存 TTL 缓存，降低交付演示时的重复调用风险。
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
- `RouteContext`：前端入口上下文，包含 `source`、`city_hint`、`anchor_text`、`anchor_location`、`selected_pois`、`transport_strategy`、`fixed_start_poi_id` 和 `pinned_policy`。
- `AgentTraceStep`：P2 新增，用于展示每一步工具调用的工具名、输入摘要、输出摘要和状态。
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

`POST /api/search-preview`

- 输入搜索页 query、历史搜索词和城市提示。
- 先解析真实地图锚点，再调用高德召回 4-8 个候选 POI，返回候选列表、默认勾选 POI 和可直接传给 `/api/plan` 的 `route_context`。
- 用于搜索页“先搜索结果，再触发 SmartRoute”的交互，避免搜索入口只是静态卡片。

`POST /api/plan`

- 输入自然语言 query、user_id、路线数量、`profile_source`、可选 `profile_id`，以及可选 `route_context`。
- `route_context` 支持搜索/小团的地点锚点、收藏夹已选 POI、POI 详情页当前商户坐标。
- POI 详情页可传 `fixed_start_poi_id` 与 `pinned_policy="fixed_start"`，路线排序、替换和调整都必须保留当前商户为第 1 站。
- 返回解析意图、用户画像、画像来源、模拟/脱敏画像上下文、候选 POI、路线方案、生成 trace、规划耗时、画像影响、冲突解释、路线完整性和结构化生成后追问。
- P2 返回 `tool_trace`，展示 LLM/规则解析、画像构建、POI 搜索、路线规划和高德路径分段。
- 真实地点模式：若 query 或 `route_context` 含明确地点/城市/坐标，候选必须来自高德或入口已选 POI；高德失败时返回空候选和失败 trace，不进入上海本地 RAG。

`POST /api/adjust`

- 输入当前路线、自然语言调整指令、用户画像模式、原始 query。
- 返回调整后的路线、调整状态、被修改的站点、调整前后指标、指标变化、调整说明、失败放宽建议、冲突解释、规划耗时和下一步追问。
- P2 返回 `tool_trace`，展示 Parse adjustment、Search replacement POI、Validate constraints、Update route、Explain changes；DeepSeek 可参与调整工具选择，无 Key 时规则兜底。

`POST /api/replace`

- 输入当前路线、需要替换的站点序号、query、user_id。
- 返回同类可替换 POI 和预算/等待/距离影响。

`POST /api/feedback`

- 输入 route 和 feedback。
- 将喜欢/不合适写入 SQLite 用户画像。

## 5. P1 / P2 状态字段

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
- `parser_source / parser_confidence / parser_reason / llm_slots`：记录需求解析来自 DeepSeek 还是规则兜底。
- `tool_trace`：P2 Agent Trace，前端用于展示 ReAct / ToolUse 链路。
- `RouteContext.transport_strategy`：入口或评委即时画像指定的交通策略，例如步行优先、公交/地铁优先、打车优先。
- `RouteContext.fixed_start_poi_id / pinned_policy`：详情页固定起点或搜索/收藏软固定策略，防止排序和调整把入口核心 POI 挪走。

## 6. P2 即时画像策略

比赛阶段预计无法获得真实美团客户数据，因此 P2 使用“评委即时画像”作为合规替代：

- 前端首次调起 SmartRoute 时弹出轻量偏好选择。
- 用户选择同行人群、预算区间、排队容忍、移动方式和内容偏好。
- 前端把选择转为 `judge-session` 脱敏画像，经 `/api/profile/import` 保存为 `manual_import`。
- 后端按照同一套 `MeituanUserContext` 参与召回和排序，不需要真实账号、cookie 或订单数据。
- 如果未来拿到官方授权，只替换 `official_api` adapter，不重写规划链路。

## 7. 与通用大模型的关系

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

## 8. 开发约束

- 不在前端硬编码路线结果。
- 不提交 `web/.env.local`、高德 Key 或其他密钥。
- 不破坏现有 `POI`、`Route`、`UserConstraints` 模型。
- 新增能力优先通过 API 扩展，而不是只改前端展示。
- 明确地点/城市/坐标的请求必须走高德 Web 服务或入口已选 POI；禁止静默回退到其他城市本地数据。
- 每条主路线需要稳定满足 >=3 POI。
- 每条主路线需要强制覆盖餐饮 + 文化/娱乐。
- 调整路线时必须保留当前路线上下文，避免表现为“重新开始”。

## 9. 当前风险

- DeepSeek Key 未配置或额度不足时，LLM 解析和工具选择会规则兜底，展示源会标记为 `fallback`。
- 当前画像支持模拟画像和脱敏手动导入画像，不是真实美团官方账号授权数据。
- 高德 Web 服务 Key 缺失、平台类型错误、IP 白名单或额度限制时，真实地点模式会返回可解释失败，不会跨城生成错误路线。无明确地点的演示场景仍可使用本地 RAG。
- 高德 `USERKEY_PLAT_NOMATCH` 表示后端误用了“Web端(JS API)”Key；`AMAP_WEB_SERVICE_KEY` 必须使用“Web服务”Key。
- 不允许通过自动登录、抓 cookie 或爬取个人账号方式获取真实画像。
