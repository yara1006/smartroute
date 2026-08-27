# SmartRoute AI

[![CI](https://github.com/yara1006/smartroute/actions/workflows/ci.yml/badge.svg)](https://github.com/yara1006/smartroute/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-200%20passing-brightgreen.svg)](tests/)
[![codecov](https://codecov.io/gh/yara1006/smartroute/branch/main/graph/badge.svg)](https://codecov.io/gh/yara1006/smartroute)

> 面向美团 AI 黑客松的本地生活路线规划插件 —— 把吃喝玩乐意图变成可执行路线。

📖 **[English](README_en.md)** · **[文档站](docs-site/)**

SmartRoute AI 不是一个独立 App，而是嵌入美团 App 的垂直能力插件。它将用户的意图、美团 POI、UGC 评价、预算、排队时间、距离和历史偏好组织成可执行的路线方案。

<!-- Feature comparison -->
![Features](docs/images/features-comparison.svg?v=2)

## 🏗️ 系统架构

![Architecture](docs/images/architecture.svg?v=2)

## ✨ 核心特性

- 🗺️ **多入口触发**：搜索页、问小团、收藏夹、POI 详情页均可调起
- 🧠 **LLM 意图解析**：DeepSeek LLM 优先，规则兜底，解析时间/预算/人数/偏好
- 📍 **真实地点规划**：高德 Web 服务驱动，拒绝跨城错误
- 📊 **多路线方案**：生成差异化路线，展示画像影响和冲突解释
- 🔄 **自然语言调整**：局部修改路线，实时展示指标变化
- 👤 **用户画像**：3 种内置画像 + 脱敏导入 + 评委即时画像
- 🧩 **Multi-Agent 架构**：意图路由 → 意图解析 → POI 检索 → 路线规划
- 📡 **Tool Trace**：ReAct / ToolUse 风格展示每一步工具调用链路
- 🔌 **MCP 协议支持**：路线规划功能暴露为标准 MCP 工具，支持跨框架 Agent 调用（Microsoft Agent Framework、LangGraph、Google ADK）

## 🏗️ 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI · Pydantic · Python 3.11+ |
| 前端 | React 19 · Vite · 高德 JS API 2.0 |
| LLM | DeepSeek（意图解析 + 调整工具选择）|
| 地图 | 高德 Web 服务（POI / 地理编码 / 路径规划）|
| 数据 | 本地 JSON + SQLite 用户画像 |
| 测试 | pytest · 200 测试 · Vitest |
| 部署 | Docker · docker-compose · GitHub Actions CI |
| 协议 | MCP (Model Context Protocol) — 跨框架 Agent 互操作 |

## 🚀 快速开始

![Terminal Demo](docs/images/terminal-demo.svg)

### 前置要求

- Python 3.11+
- Node.js 20+
- （可选）DeepSeek API Key
- （可选）高德 Web 服务 Key

### 后端

```bash
# 克隆项目
git clone https://github.com/yara1006/smartroute.git
cd smartroute

# 安装 Python 依赖
pip install -r requirements.txt

# 初始化种子数据（生成 500 条模拟 POI）
python data/seed_db.py

# 启动 FastAPI（端口 8000）
python -m uvicorn api:app --host 127.0.0.1 --port 8000
# 或使用 Makefile
make run
```

### 前端

```bash
cd web
npm install
npm run dev
# 或使用 Makefile（在项目根目录）
make run-web
```

访问 http://127.0.0.1:5173

### 环境变量（可选）

```bash
# .env — 后端
DEEPSEEK_API_KEY=your-key          # 启用 LLM 意图解析
AMAP_WEB_SERVICE_KEY=your-key      # 启用真实地点 POI 召回

# web/.env.local — 前端
VITE_AMAP_KEY=your-js-api-key
VITE_AMAP_SECURITY_JS_CODE=your-code
```

无 Key 时所有功能均可降级运行，不影响 Demo 跑通。

## 📁 项目结构

```
smartroute/
├── api.py                   # FastAPI 路由层
├── schemas.py               # Pydantic 请求/响应模型
├── core/
│   ├── config.py            # 集中配置（Settings 单例）
│   ├── logging_config.py    # 结构化日志
│   ├── models.py            # 核心数据模型
│   ├── agents/              # Multi-Agent 系统
│   │   ├── route_intent_router.py
│   │   ├── intent_parser.py
│   │   ├── poi_retriever.py
│   │   └── route_planner.py
│   ├── services/
│   │   └── amap_client.py   # 高德 Web 服务客户端
│   ├── rag/
│   │   └── vector_store.py  # 本地向量检索
│   └── memory/
│       └── user_profile.py  # SQLite 用户画像
├── services/                # 业务逻辑服务层
│   ├── route_service.py     # 统一导出 facade
│   ├── profile_service.py   # 画像管理
│   ├── anchor_service.py    # 地点/锚点解析
│   ├── route_builder.py     # 动态路线构建
│   ├── adjustment_service.py# 路线调整
│   ├── trace_service.py     # Tool trace
│   ├── safety_reviewer.py   # 安全边界拦截
│   └── route_insight.py     # 路线分析/指标
├── scripts/                 # 可执行脚本
│   ├── cli.py               # CLI 入口（L6 通道层）
│   ├── mcp_server.py        # MCP 工具服务器
│   └── deploy.sh            # 部署脚本
── web/                     # React 前端
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── Panels.jsx
│       │   ├── PhoneExperience.jsx
│       │   ├── RouteMap.jsx
│       │   ├── QueryComposer.jsx
│       │   └── ErrorBoundary.jsx
│       ├── api.js
│       ├── helpers.js
│       └── constants.js
├── tests/                   # pytest 后端测试（200 个）
├── .github/workflows/       # CI/CD
│   ├── ci.yml               # Lint + 多版本测试 + 前端构建
│   └── release.yml          # 自动 Release
└── docs/                    # 项目文档
    ├── ARCHITECTURE.md
    ├── API.md
    ├── PRD.md
    └── DESIGN.md
```

## 🧪 测试

```bash
# 后端测试（200 个用例，覆盖率 ≥ 60%）
pytest tests/ -v
# 或使用 Makefile
make test

# 带覆盖率报告
make test-cov

# 前端测试
cd web && npm test

# Lint
make lint
```

## 📖 文档

| 文档 | 说明 |
|------|------|
| [架构说明](docs/ARCHITECTURE.md) | 技术架构、Agent 链路、服务层模块 |
| [API 参考](docs/API.md) | 所有 HTTP 接口详细说明 |
| [产品需求](docs/PRD.md) | 产品定位、用户痛点、评分标准 |
| [设计规范](docs/DESIGN.md) | 美团内嵌插件交互规范 |
| [部署指南](docs/DEPLOYMENT.md) | Docker 部署、服务器配置 |
| [变更日志](CHANGELOG.md) | 版本变更记录 |
| [贡献指南](CONTRIBUTING.md) | 如何参与项目开发 |
| [安全策略](SECURITY.md) | 漏洞报告流程 |

## 🐳 Docker 部署

```bash
# 构建并启动
docker-compose up -d

# 或使用 Makefile
make build
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解开发流程和代码规范。

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 开源。

## 🙏 致谢

- 美团 AI 黑客松组委会
- 高德开放平台
- DeepSeek API
