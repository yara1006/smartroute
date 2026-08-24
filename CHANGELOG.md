# Changelog

本项目的所有重要变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

## [Unreleased]

### Added

- 待补充

## [0.2.0] - 2026-08-24

### Added

- 新增完整的测试套件，覆盖核心业务逻辑，共计 200+ 测试用例
- 新增 CI/CD 流水线（GitHub Actions），包含自动测试、Lint 检查和构建部署
- 新增前端 React（Vite）界面，支持交互式路径规划
- 新增 Docker 部署支持（Dockerfile + docker-compose.yml）
- 新增健康检查端点 `/api/health`
- 新增 Makefile 提供常用开发命令快捷入口

### Changed

- **重大重构**：将 `api.py` 拆分为独立的服务层模块（`services/`、`core/`、`schemas.py`）
- 前端从单文件拆分为组件化架构（`web/src/components/`、`web/src/services/`）
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

[Unreleased]: https://github.com/origin/smartroute/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/origin/smartroute/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/origin/smartroute/releases/tag/v0.1.0
