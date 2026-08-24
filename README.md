# SmartRoute AI

## 项目链接

- 项目文档：https://pan.baidu.com/s/1bAIzRwzzNYDD4qt8w6-B8g?pwd=aa65
- 在线访问：http://42.193.138.163

SmartRoute AI 是一个面向美团 AI 黑客松的本地生活路线规划插件 / 子 Agent。它不是独立 App，也不是替代小团 AI 的通用聊天助手，而是嵌入美团 App 的垂直能力：把用户的吃喝玩乐意图、美团 POI、UGC、预算、排队、时间、距离和历史偏好组织成可执行路线。

它既支持用户已经选中多个 POI 后“一键排路线”，也支持用户未知具体 POI 时直接说：

```text
我下午要去深圳大学附近玩3个小时，帮我规划一个路线
```

最终 Web Demo 会以“美团 App 场景模拟器 + SmartRoute 插件弹出”的方式展示：搜索页、问小团、收藏夹、POI 详情页都能调起同一个 SmartRoute 路线规划 Agent。其中问小团仍保持通用 AI 助手界面，不默认展示路线规划 prompt；只有当路线意图识别命中时，才调起 SmartRoute 插件卡。

## 竞品与替代方案

用户现在可能会用 DeepSeek / 豆包等通用大模型、美团/点评搜索、高德/百度地图，或圆周旅迹等旅行路线规划工具解决类似问题。SmartRoute 的差异是：它不只给文本建议，也不只做导航，而是把美团 POI、UGC、价格、排队、营业时间、用户画像和履约工具链结合起来，输出可执行路线、替换项和反馈闭环。

## 运行

```bash
pip install -r requirements.txt
python data/seed_db.py
streamlit run app.py
```

应用会生成 500 条本地模拟 POI，并建立本地检索索引。没有 DeepSeek API Key 也能运行；配置 Key 后会启用 LLM 意图解析和调整工具选择，无 Key 时自动规则兜底。

产品级演示要求：当用户明确给出城市、地标、商圈、收藏 POI 或 POI 详情页坐标时，后端必须优先使用高德 Web 服务解析锚点、召回真实 POI 和计算路径。高德失败时不会再静默回退到上海本地 RAG，避免出现“北京问题生成上海路线”的跨城错误；系统会返回清晰的配置或调用失败提示。

## 当前能力

- Web Demo 以“搜索页 / 问小团 / 收藏夹 / POI 详情页”四个美团入口调起 SmartRoute 插件
- 四个入口会把真实上下文传给后端：小团/搜索传地点锚点，收藏夹传已选 POI，详情页传当前商户坐标
- 搜索页已接入 `/api/search-preview`：先按搜索词、历史搜索和城市锚点召回 4-8 个真实候选 POI，用户勾选后再生成路线
- POI 详情页支持固定起点：从当前店出发时会传 `fixed_start_poi_id`，路线排序和后续调整都必须保留该店为第 1 站
- 小团入口支持路线意图识别：优先 DeepSeek，失败或无 Key 时规则兜底
- 自然语言解析时间、预算、人数、排队、区域和偏好；`IntentParserAgent` 已支持 DeepSeek LLM 优先 + 规则兜底
- 本地 POI 检索与多条件过滤
- 主路线稳定生成 >=3 个 POI
- 主路线覆盖餐饮/咖啡 + 景点/娱乐
- 生成 2 条差异化路线
- 支持三种模拟美团用户画像：低排队务实型、文艺体验型、带爸妈轻松型
- 支持脱敏真实画像导入：手动整理搜索词、收藏 POI、浏览偏好、预算、排队和步行偏好后导入，不登录账号、不抓 cookie
- 支持评委即时画像弹窗：首次调起 SmartRoute 时选择同行人群、预算、排队、交通和内容偏好，生成 `judge-session` 临时画像
- 展示“画像信号 → 召回加权 → 路线变化”，说明为什么不同画像会得到不同路线
- 支持自然语言局部调整：少走路、便宜点、不要排队、加晚餐/咖啡/展览；`/api/adjust` 返回 ReAct / ToolUse 风格 `tool_trace`
- 展示规划耗时、路线完整性、冲突解释和结构化生成后追问
- 展示调整状态、调整前后指标变化、站点变化和失败时的约束放宽建议
- 高德地图展示站点与路线；后端支持高德 Web 服务 POI 文本搜索、地理编码、周边 POI 和步行/公交/打车策略化路径规划
- 高德 Web 服务调用已增加 30 分钟内存 TTL 缓存，减少交付演示时重复搜索导致 QPS/配额触发的风险
- 明确地点场景采用真实地点模式：优先返回 `source=amap` 的真实 POI；高德失败时返回失败 trace，不跨城回退到本地 RAG
- 同类 POI 替换，展示预算/等待/距离影响
- SQLite 记录用户反馈和偏好

## 当前待补齐

- 当前支持模拟画像和脱敏手动导入画像；不接真实美团账号授权、真实搜索历史或收藏接口
- 明确地点/城市/入口上下文场景依赖高德 Web 服务 Key；Key 缺失、类型错误或权限不匹配时，系统会提示失败原因，不再生成错误城市路线
- `official_api` 仍是预留 adapter；没有美团或大赛方授权时，不读取真实客户数据
- Stitch 仅作为移动端视觉设计参考或高保真稿生成工具，不作为最终部署平台；线上 Demo 仍由当前 Vite + FastAPI 承接真实后端 API

### DeepSeek API Key

1. 打开 DeepSeek Platform，进入 API Keys 页面创建 Key。
2. 在项目根目录新建或编辑 `.env`，填入：

```bash
DEEPSEEK_API_KEY=你的DeepSeekKey
DEEPSEEK_CHAT_MODEL=deepseek-chat
DEEPSEEK_ROUTE_MODEL=deepseek-reasoner
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

3. 重启 FastAPI 后端。Key 只放后端 `.env`，不要写进前端代码，也不要提交 GitHub。

无 Key 时，路线意图识别、路线需求解析和调整链路都会降级为本地规则，不影响 Demo 跑通。

## 产品化前端 Demo

方案 B 使用 React/Vite 做高保真产品界面，接入真实 Python 后端数据。

后端 API：

```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m uvicorn api:app --host 127.0.0.1 --port 8000
```

前端：

```bash
cd web
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。页面会请求 `/api/search-preview`、`/api/plan`、`/api/adjust`、`/api/replace`、`/api/feedback`，搜索候选、路线、局部调整、替换项和用户画像都来自当前后端链路。

### 脱敏画像导入

P1c 支持在前端粘贴 JSON 导入你和队友手动整理的脱敏画像。可包含：

```json
{
  "display_name": "Xiangyue 脱敏样本",
  "recent_searches": ["外滩展览", "咖啡", "下午茶"],
  "favorite_pois": ["seed by seed 囍得咖啡酒馆", "海派光影展馆"],
  "browsed_pois": ["安静", "有设计感", "拍照出片"],
  "favorite_categories": ["咖啡/茶饮", "景点"],
  "favorite_districts": ["黄浦区"],
  "budget_preference": 220,
  "max_wait_preference": 18,
  "walk_preference": "适中",
  "coupon_sensitive": false
}
```

不要导入手机号、真实姓名、账号密码、cookie、token、订单号或精确住址。后端会拒绝明显敏感字段，并将画像归一化为 `MeituanUserContext`。

### 高德地图

前端已接入高德 JS API 2.0；后端 P1d/P2 支持高德 Web 服务，用于地点解析、周边 POI 召回和路径规划。

注意：前端高德 JS API Key 和后端高德 Web 服务 Key 是两个不同平台的 Key。后端 `.env` 的 `AMAP_WEB_SERVICE_KEY` 必须是“Web服务”Key；如果误填成“Web端(JS API)”Key，高德会返回 `USERKEY_PLAT_NOMATCH`，真实地点路线无法生成。

在 `web/.env.local` 中配置：

```bash
VITE_API_BASE=http://127.0.0.1:8000
VITE_AMAP_KEY=你的高德Web端Key
VITE_AMAP_SECURITY_JS_CODE=你的高德安全密钥
```

在项目根目录 `.env` 或环境变量中配置后端 Web 服务 Key：

```bash
AMAP_WEB_SERVICE_KEY=你的高德Web服务Key
```

配置后重启后端和 `npm run dev`，路线结果里的地图会使用高德底图、站点 marker，并优先使用高德 Web 服务返回的 POI 和道路 polyline。

后端 Web 服务 Key 可用性验证：

```bash
source .env
curl "https://restapi.amap.com/v5/place/text?keywords=北京金鱼胡同&region=北京&page_size=3&key=$AMAP_WEB_SERVICE_KEY"
```

返回 `status=1` 才说明后端 Web 服务 Key 可用于真实 POI 召回。

不要提交 `web/.env.local` 到 GitHub。

## 测试

```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_pipeline.py tests/test_api.py -q
cd web
npm run build
```

## 文档

- [PRD](docs/PRD.md)：产品定位、用户痛点、MVP、评分标准映射
- [Design](docs/DESIGN.md)：美团内嵌插件动线、移动端/桌面端设计规范
- [Architecture](docs/ARCHITECTURE.md)：技术栈、Agent 链路、API、数据模型
- [TODO](docs/TODO.md)：下一步开发任务和验收提醒
- [Deployment](docs/DEPLOYMENT.md)：服务器部署、GitHub 同步和自动部署
