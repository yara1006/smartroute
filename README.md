# SmartRoute AI

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

应用会生成 500 条上海模拟 POI，并建立本地检索索引。没有 DeepSeek API Key 也能运行；后续可以把意图解析和路线规划替换为 DeepSeek Function Calling。

## 当前能力

- Web Demo 以“搜索页 / 问小团 / 收藏夹 / POI 详情页”四个美团入口调起 SmartRoute 插件
- 四个入口会把真实上下文传给后端：小团/搜索传地点锚点，收藏夹传已选 POI，详情页传当前商户坐标
- 小团入口支持路线意图识别：优先 DeepSeek，失败或无 Key 时规则兜底
- 自然语言解析时间、预算、人数、排队、区域和偏好
- 本地 POI 检索与多条件过滤
- 主路线稳定生成 >=3 个 POI
- 主路线覆盖餐饮/咖啡 + 景点/娱乐
- 生成 2 条差异化路线
- 支持三种模拟美团用户画像：低排队务实型、文艺体验型、带爸妈轻松型
- 支持脱敏真实画像导入：手动整理搜索词、收藏 POI、浏览偏好、预算、排队和步行偏好后导入，不登录账号、不抓 cookie
- 展示“画像信号 → 召回加权 → 路线变化”，说明为什么不同画像会得到不同路线
- 支持自然语言局部调整：少走路、便宜点、不要排队、加晚餐/咖啡/展览
- 展示规划耗时、路线完整性、冲突解释和结构化生成后追问
- 展示调整状态、调整前后指标变化、站点变化和失败时的约束放宽建议
- 高德地图展示站点与路线；后端支持高德 Web 服务地理编码、周边 POI 和路径规划，未配置 Key 时按用户锚点生成本地兜底路线
- 同类 POI 替换，展示预算/等待/距离影响
- SQLite 记录用户反馈和偏好

## 当前待补齐

- 当前支持模拟画像和脱敏手动导入画像；不接真实美团账号授权、真实搜索历史或收藏接口
- DeepSeek Function Calling / ToolUse 尚未接入调整链路
- 高德 Web 服务 Key 未配置时，真实 POI 和真实道路 polyline 会降级为锚点附近兜底 POI 与估算路径

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

打开 `http://127.0.0.1:5173`。页面会请求 `/api/plan`、`/api/adjust`、`/api/replace`、`/api/feedback`，路线、候选 POI、局部调整、替换项和用户画像都来自当前后端链路。

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

前端已接入高德 JS API 2.0；后端 P1d 支持高德 Web 服务，用于地点解析、周边 POI 召回和路径规划。没有配置 Key 时会自动降级为锚点附近本地兜底路线，不影响路线生成。

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
