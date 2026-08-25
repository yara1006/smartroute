# CLAUDE.md — SmartRoute AI Project Rules

## WHAT

SmartRoute AI 是一个多智能体本地生活路线规划系统，将用户的自然语言出行意图转化为可执行路线。
技术栈：FastAPI + React 19 + DeepSeek LLM + 高德 Web 服务 + SQLite 用户画像。

## WHY — 不可变约束

- **安全边界**：系统绝不自动执行预订、付款、保存敏感凭据（身份证/银行卡/密码）等高风险动作。
  所有高风险操作必须返回 `safety_warnings` 并设置 `refused=true`。
- **跨城防护**：有明确城市/地标/坐标的请求必须走高德 Web 服务，禁止静默回退到其他城市本地 RAG。
- **数据隐私**：不提交 `.env`、`web/.env.local`、高德 Key、DeepSeek Key 到 Git。
  用户画像只存脱敏数据，不含手机号/账号/cookie。
- **成本上限**：LLM 调用有超时限制（10s），高德 API 有 30 分钟 TTL 缓存防止 QPS 超限。

## HOW — 安装、运行、测试、调试

### 安装
```bash
pip install -r requirements.txt
cd web && npm install
```

### 运行
```bash
# 后端（端口 8000）
make run
# 前端（端口 5173）
make run-web
# Docker
docker-compose up -d
```

### 测试
```bash
# 后端（200+ 测试，覆盖率 ≥ 80%）
make test
make test-cov
# 前端（48 测试）
cd web && npm test
# 评测（20 条 eval case）
python -c "from core.eval import EVAL_CASES; print(len(EVAL_CASES))"
```

### 调试
- 启动时日志会打印 `deepseek_enabled` / `amap_enabled` / `cors_origins` 状态。
- `/api/docs` 是 FastAPI 自动生成的交互式 API 文档。
- `examples/quickstart.py` 包含 5 个端到端 API 调用示例。

## TEST — 改代码必须同步验证什么

- 改 `services/` 或 `core/agents/` 后必须跑 `make test`，覆盖率不得低于 80%。
- 改 `api.py` 路由后必须验证 `/api/health` 返回正常。
- 改 `web/src/` 后必须跑 `cd web && npm test && npm run build`。
- 改 `schemas.py` 后必须验证所有测试通过，因为 schema 变更影响前后端。
- 外部依赖（高德/DeepSeek）用 monkeypatch 模拟，测试不依赖真实 API Key。

## 项目结构速查

```
api.py                    # FastAPI 路由层（~800 行）
schemas.py                # Pydantic 请求/响应模型
core/
  config.py               # Settings 单例，集中配置
  models.py               # 核心数据模型（POI、Route 等）
  agents/                 # Multi-Agent 系统（4 个 Agent）
  services/amap_client.py # 高德 Web 服务客户端（TTL 缓存）
  rag/vector_store.py     # 本地向量检索
  memory/user_profile.py  # SQLite 画像
  eval/eval_cases.py      # 20 条 eval case + 5 个指标
services/                 # 业务逻辑层（6 个模块）
  route_service.py        # 统一 re-export facade
  profile_service.py      # 画像管理
  anchor_service.py       # 地点/锚点解析
  route_builder.py        # 动态路线构建
  adjustment_service.py   # 路线调整
  trace_service.py        # Tool trace
  safety_reviewer.py      # 安全边界拦截
  route_insight.py        # 路线分析/指标
cli.py                    # CLI 入口（L6 通道层）
web/                      # React 前端
docs/                     # 项目文档
  RETROSPECTIVE.md        # 复盘文档（trade-off 决策记录）
docs-site/                # VitePress 文档站
```

## 编码规范

- Python 用 ruff 格式化，行宽 120。
- 所有公开函数和类必须有 docstring。
- 新服务模块放在 `services/`，通过 `route_service.py` re-export。
- 新 Agent 放在 `core/agents/`，在 `api.py` 的 `load_agents()` 中初始化。
- 新 API 路由在 `api.py` 添加，同步更新 `docs/API.md` 和 `docs-site/reference/api.md`。
- 新 schema 在 `schemas.py` 添加，同步更新前后端。
