# 部署

## Docker 部署（推荐）

```bash
docker-compose up -d
```

服务将在端口 8000 启动，数据持久化到 `./data` 目录。

## 手动部署

```bash
# 后端
pip install -r requirements.txt
python data/seed_db.py
python -m uvicorn api:app --host 0.0.0.0 --port 8000

# 前端（生产构建）
cd web
npm ci
npm run build
# 将 web/dist 部署到静态文件服务器
```

## 生产环境变量

```bash
DEEPSEEK_API_KEY=your-key
AMAP_WEB_SERVICE_KEY=your-key
CORS_ORIGINS=https://your-domain.com,https://app.your-domain.com
```

## GitHub Actions CI

每次 push 到 `main` 或 PR 自动触发：

1. **Lint** — ruff check + format + mypy
2. **Test** — Python 3.11 / 3.12 / 3.13 矩阵测试 + 覆盖率
3. **Frontend** — npm ci + vitest + build

## 发布新版本

1. 更新 `CHANGELOG.md`，将 `Unreleased` 内容移到新版本号下
2. 创建并推送 tag：
   ```bash
   git tag v0.3.0
   git push origin v0.3.0
   ```
3. GitHub Actions 自动创建 Release 并推送 Docker 镜像到 `ghcr.io`
