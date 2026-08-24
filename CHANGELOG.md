# Changelog

本项目的所有重要变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

## [Unreleased]

### Added

- 全量 Python 模块 Docstring 覆盖（14 个模块，49 个类，50+ 公开方法）
- `core/config.py` 集中配置单例，统一管理环境变量与路径
- `core/logging_config.py` 结构化日志（`setup_logging()`、`get_logger()`）
- `.pre-commit-config.yaml`（ruff + ruff-format）
- `docs/API.md` 完整 API 参考文档
- `CODE_OF_CONDUCT.md`（Contributor Covenant v2.1）
- GitHub Release 自动化 workflow
- 前端 Vitest 测试基础设施

### Changed

- 重写 `README.md`：新增徽章、Quick Start、项目结构、文档索引
- 重写 `docs/ARCHITECTURE.md`：反映当前服务层架构（services/ 6 个模块）
- CORS 来源改为从 `CORS_ORIGINS` 环境变量读取，支持生产环境多域名
- TSP 路线排序从 O(n!) 全排列改为 O(n²) 贪心最近邻算法

### Fixed

- 移除所有裸 `except: pass`，改为显式异常捕获与日志记录
- AMap 缓存增加 `AMAP_CACHE_MAX_ENTRIES=500` 上限，防止内存无界增长
- 缓存增加 `_evict_expired_cache()` 定期清理过期条目
- `route_builder.py` 跨模块依赖（`city_hint_from` 等）补充显式导入

## [0.2.0] - 2026-08-24

### Added

- 新增完整的测试套件，覆盖核心业务逻辑，共计 200+ 测试用例
- 新增 CI/CD 流水线（GitHub Actions），包含自动测试、Lint 检查和构建部署
- 新增前端 React（Vite）界面，支持交互式路径规划
- 新增 Docker 部署支持（Dockerfile + docker-compose.yml）
- 新增健康检查端点 `/api/health`
- 新增 Makefile 提供常用开发命令快捷入口
- `CONTRIBUTING.md`、`SECURITY.md`、`CHANGELOG.md`、`LICENSE`（MIT）
- Issue 模板（Bug Report / Feature Request）与 PR 模板
- Python 多版本 CI 测试矩阵（3.11 / 3.12 / 3.13）

### Changed

- **重大重构**：将 `api.py`（2868 行）拆分为独立的服务层模块（`services/`、`core/`、`schemas.py`）
- `api.py` 缩减至 ~813 行，仅保留路由层
- 前端 `App.jsx` 从 2691 行拆分为组件化架构（`web/src/components/`、`web/src/api.js`、`helpers.js`、`constants.js`）
- 项目结构重新组织，职责分离更加清晰
- API 接口路径统一调整为 `/api/` 前缀
- 错误处理机制全面升级，统一异常响应格式

### Fixed

- 修复高德 API 超时时的重试逻辑
- 修复多站点路径规划结果不稳定的问题
- 修复前端在生产环境下静态资源路径错误

## [0.1.0] - 2026-05-28

### Added

- 首个可用版本，Hackathon 发布
- 基于高德地图 API 的路线规划功能
- 支持多站点路径优化
- FastAPI 后端，提供 RESTful 接口
- 基础的前端页面
- 支持美团外卖配送场景的路径规划

[Unreleased]: https://github.com/yara1006/smartroute/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/yara1006/smartroute/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/yara1006/smartroute/releases/tag/v0.1.0
