# CLAUDE.md — SmartRoute AI Project Rules

## WHAT

SmartRoute AI is a multi-agent local-life route planning system that converts user's natural language travel intentions into executable itineraries.

Tech stack: FastAPI + React 19 + DeepSeek LLM + AMap Web Service + SQLite user profiles.

## WHY — Immutable Constraints

- **Safety boundaries**: System must NEVER auto-execute booking, payment, or save sensitive credentials (ID card/bank card/password). All high-risk operations must return `safety_warnings` and set `refused=true`.
- **Cross-city protection**: Requests with clear city/landmark/coordinates MUST use AMap Web Service; silent fallback to other city's local RAG is PROHIBITED.
- **Data privacy**: Do NOT commit `.env`, `web/.env.local`, AMap keys, DeepSeek keys to Git. User profiles only store desensitized data, no phone/account/cookie.
- **Cost limits**: LLM calls have 10s timeout; AMap API has 30-minute TTL cache to prevent QPS limit.

## HOW — Install, Run, Test, Debug

### Install
```bash
pip install -r requirements.txt
cd web && npm install
```

### Run
```bash
# Backend (port 8000)
make run
# Frontend (port 5173)
make run-web
# Docker
docker-compose up -d
```

### Test
```bash
# Backend (200+ tests, coverage ≥ 80%)
make test
make test-cov
# Frontend (48 tests)
cd web && npm test
# Eval (20 eval cases)
python -c "from core.eval import EVAL_CASES; print(len(EVAL_CASES))"
```

### Debug
- Startup logs print `deepseek_enabled` / `amap_enabled` / `cors_origins` status
- `/api/docs` is FastAPI auto-generated interactive API docs
- `examples/quickstart.py` contains 5 end-to-end API call examples

## TEST — What Must Be Verified When Changing Code

- After changing `services/` or `core/agents/`: MUST run `make test`, coverage must NOT drop below 80%
- After changing `api.py` routes: MUST verify `/api/health` returns normal
- After changing `web/src/`: MUST run `cd web && npm test && npm run build`
- After changing `schemas.py`: MUST verify all tests pass (schema changes affect frontend/backend)
- External dependencies (AMap/DeepSeek) use monkeypatch mocking; tests do NOT depend on real API keys

## Project Structure Quick Reference

```
api.py                    # FastAPI route layer (~800 lines)
schemas.py                # Pydantic request/response models
core/
  config.py               # Settings singleton
  models.py               # Core data models (POI, Route, etc.)
  agents/                 # Multi-Agent system (4 agents)
  services/amap_client.py # AMap Web Service client (TTL cache)
  rag/vector_store.py     # Local vector retrieval
  memory/user_profile.py  # SQLite profiles
  eval/eval_cases.py      # 20 eval cases + 5 metrics
services/                 # Business logic layer (6 modules)
  route_service.py        # Unified re-export facade
  profile_service.py      # Profile management
  anchor_service.py       # Location/anchor resolution
  route_builder.py        # Dynamic route construction
  adjustment_service.py   # Route adjustment
  trace_service.py        # Tool trace
  safety_reviewer.py      # Safety boundary intercept
  route_insight.py        # Route analysis/metrics
cli.py                    # CLI entry (L6 channel layer)
web/                      # React frontend
docs/                     # Project docs
  RETROSPECTIVE.md        # Retrospective (trade-off decisions)
docs-site/                # VitePress documentation site
```

## Coding Standards

- Python uses ruff formatting, line width 120
- All public functions and classes MUST have docstrings
- New service modules go in `services/`, re-export via `route_service.py`
- New agents go in `core/agents/`, initialize in `api.py`'s `load_agents()`
- New API routes added in `api.py`, sync update `docs/API.md` and `docs-site/reference/api.md`
- New schemas added in `schemas.py`, sync update frontend/backend
