# 快速开始

## 前置要求

- Python 3.11+
- Node.js 20+
- （可选）DeepSeek API Key
- （可选）高德 Web 服务 Key

## 安装

```bash
git clone https://github.com/yara1006/smartroute.git
cd smartroute

# 后端依赖
pip install -r requirements.txt

# 初始化种子数据（生成 500 条模拟 POI）
python data/seed_db.py

# 前端依赖
cd web && npm install
```

## 启动开发环境

**后端**（端口 8000）：

```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload
# 或
make run
```

**前端**（端口 5173）：

```bash
cd web && npm run dev
# 或（项目根目录）
make run-web
```

访问 [http://127.0.0.1:5173](http://127.0.0.1:5173)

## 环境变量

创建 `.env` 文件（后端）：

```bash
DEEPSEEK_API_KEY=your-key          # 启用 LLM 意图解析
AMAP_WEB_SERVICE_KEY=your-key      # 启用真实地点 POI 召回
```

创建 `web/.env.local`（前端）：

```bash
VITE_AMAP_KEY=your-js-api-key
VITE_AMAP_SECURITY_JS_CODE=your-code
```

> 无 API Key 时所有功能均可降级运行，不影响 Demo 跑通。

## 运行测试

```bash
# 后端（200 个测试，覆盖率 ≥ 80%）
make test

# 带覆盖率报告
make test-cov

# 前端（46 个测试）
cd web && npm test
```
