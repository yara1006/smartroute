# SmartRoute AI

[![CI](https://github.com/yara1006/smartroute/actions/workflows/ci.yml/badge.svg)](https://github.com/yara1006/smartroute/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-200%20passing-brightgreen.svg)](tests/)
[![codecov](https://codecov.io/gh/yara1006/smartroute/branch/main/graph/badge.svg)](https://codecov.io/gh/yara1006/smartroute)

> A local-life route planning agent for Meituan AI Hackathon — turning food, fun, and travel intentions into executable routes.

📖 **[中文文档](README.md)**

SmartRoute AI is a vertical capability plugin embedded in the Meituan App. It organizes user intentions, Meituan POIs, UGC reviews, budgets, queue times, distances, and historical preferences into executable route plans.

<!-- Feature comparison -->
![Features](docs/images/features-comparison.svg?v=2)

##  Key Features

- 🗺️ **Multiple Entry Points**: Search, XiaoTuan chat, Favorites, POI detail page
- 🧠 **LLM Intent Parsing**: DeepSeek LLM with rules fallback; parses time, budget, party size, preferences
- 📍 **Real Location Planning**: Powered by AMap Web Service; prevents cross-city errors
- 📊 **Multiple Route Options**: Generates differentiated routes with profile influence and conflict explanations
- 🔄 **Natural Language Adjustment**: Modify routes on the fly, see real-time metric changes
- 👤 **User Profiles**: 3 built-in profiles + desensitized import + judge session profiles
- 🧩 **Multi-Agent Architecture**: Intent routing → intent parsing → POI retrieval → route planning
- 📡 **Tool Trace**: ReAct / ToolUse style display of every tool invocation step
- 🔌 **MCP Protocol Support**: Route planning exposed as standard MCP tools for cross-framework Agent calls (Microsoft Agent Framework, LangGraph, Google ADK)

## 🏗️ Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI · Pydantic · Python 3.11+ |
| Frontend | React 19 · Vite · AMap JS API 2.0 |
| LLM | DeepSeek (intent parsing + adjustment tool selection) |
| Maps | AMap Web Service (POI search / geocoding / route planning) |
| Data | Local JSON + SQLite user profiles |
| Testing | pytest · 200 tests · Vitest |
| Deployment | Docker · docker-compose · GitHub Actions CI |
| Protocol | MCP (Model Context Protocol) — Cross-framework Agent interoperability |

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- (Optional) DeepSeek API Key
- (Optional) AMap Web Service Key

### Backend

```bash
# Clone the project
git clone https://github.com/yara1006/smartroute.git
cd smartroute

# Install Python dependencies
pip install -r requirements.txt

# Initialize seed data (generates 500 mock POIs)
python data/seed_db.py

# Start FastAPI (port 8000)
python -m uvicorn api:app --host 127.0.0.1 --port 8000
# Or use Makefile
make run
```

### Frontend

```bash
cd web
npm install
npm run dev
# Or use Makefile (from project root)
make run-web
```

Visit http://127.0.0.1:5173

### Environment Variables (Optional)

```bash
# .env — backend
DEEPSEEK_API_KEY=your-key          # Enable LLM intent parsing
AMAP_WEB_SERVICE_KEY=your-key      # Enable real location POI retrieval

# web/.env.local — frontend
VITE_AMAP_KEY=your-js-api-key
VITE_AMAP_SECURITY_JS_CODE=your-code
```

All features degrade gracefully without API keys — the demo runs fully offline.

## 📁 Project Structure

```
smartroute/
├── api.py                   # FastAPI route handlers
├── schemas.py               # Pydantic request/response models
├── core/
│   ├── config.py            # Centralized Settings singleton
│   ├── models.py            # Core data models
│   ├── agents/              # Multi-Agent system
│   │   ├── route_intent_router.py
│   │   ├── intent_parser.py
│   │   ├── poi_retriever.py
│   │   └── route_planner.py
│   ├── services/
│   │   └── amap_client.py   # AMap Web Service client
│   ├── rag/
│   │   └── vector_store.py  # Local vector retrieval
│   └── memory/
│       └── user_profile.py  # SQLite user profiles
├── services/                # Business logic layer
│   ├── route_service.py     # Unified re-export facade
│   ├── profile_service.py   # Profile management
│   ├── anchor_service.py    # Location/anchor resolution
│   ├── route_builder.py     # Dynamic route construction
│   ├── adjustment_service.py# Route adjustment
│   ├── trace_service.py     # Tool trace
│   └── route_insight.py     # Route analysis/metrics
├── web/                     # React frontend
├── tests/                   # pytest backend tests (200)
└── docs/                    # Project documentation
```

## 🧪 Testing

```bash
# Backend tests (200 cases, coverage ≥ 80%)
pytest tests/ -v
# Or use Makefile
make test

# With coverage report
make test-cov

# Frontend tests
cd web && npm test
```

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | Technical architecture, agent pipeline, service layer |
| [API Reference](docs/API.md) | All HTTP endpoints documented |
| [PRD](docs/PRD.md) | Product positioning, user pain points, scoring criteria |
| [Design Spec](docs/DESIGN.md) | Meituan embedded plugin interaction design |
| [Deployment](docs/DEPLOYMENT.md) | Docker deployment, server configuration |
| [Changelog](CHANGELOG.md) | Version history |
| [Contributing](CONTRIBUTING.md) | Development workflow and code standards |

Full documentation site: `cd docs-site && npm install && npm run dev`

## 🐳 Docker Deployment

```bash
docker-compose up -d
# Or use Makefile
make build
```

## 🤝 Contributing

Issues and Pull Requests are welcome!

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and code standards.

## 📄 License

This project is licensed under the [MIT License](LICENSE).

## 🙏 Acknowledgments

- Meituan AI Hackathon Organizing Committee
- AMap Open Platform
- DeepSeek API
