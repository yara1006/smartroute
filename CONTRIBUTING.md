# 贡献指南

感谢你对 SmartRoute 项目的关注！我们欢迎各种形式的贡献，包括代码提交、Bug 修复、文档改进和功能建议。

## 如何开始

### 1. Fork 仓库

点击 GitHub 页面右上角的 **Fork** 按钮，将仓库复制到你的 GitHub 账号下。

### 2. Clone 到本地

```bash
git clone https://github.com/<你的用户名>/smartroute.git
cd smartroute
```

### 3. 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装开发依赖（测试工具、lint 工具等）
pip install pytest ruff mypy pytest-cov

# 安装前端依赖
cd web && npm install
```

### 4. 配置上游仓库

```bash
git remote add upstream https://github.com/origin/smartroute.git
```

## 开发流程

### 分支命名规范

从 `main` 分支创建特性分支，命名格式如下：

| 类型 | 格式 | 示例 |
|------|------|------|
| 新功能 | `feat/xxx` | `feat/route-optimization` |
| Bug 修复 | `fix/xxx` | `fix/timeout-error` |
| 文档更新 | `docs/xxx` | `docs/api-reference` |
| 重构 | `refactor/xxx` | `refactor/service-layer` |
| 测试 | `test/xxx` | `test/route-service` |

```bash
git checkout -b feat/your-feature-name
```

### 开发建议

- 保持分支小而聚焦，避免一个分支做太多事情
- 定期从上游 `main` 同步最新代码：`git pull upstream main`
- 提交前确保本地测试通过

## 代码规范

### Python

项目使用 **ruff** 进行代码检查和格式化，**mypy** 进行类型检查：

```bash
# 检查代码
ruff check .
ruff format --check .
mypy .

# 自动修复
ruff check --fix .
ruff format .
```

规范要点：
- 遵循 PEP 8 风格指南
- 使用类型注解（Type Hints）
- 函数和类需要添加文档字符串（docstring）
- 行宽限制为 120 字符

### JavaScript / TypeScript

项目使用 **Prettier** 进行代码格式化：

```bash
cd web
npx prettier --write .
```

规范要点：
- 使用 ESLint + Prettier 配置
- 组件使用函数式写法
- 保持导入顺序整洁

## 提交规范

本项目采用 [Conventional Commits](https://www.conventionalcommits.org/) 规范。提交信息格式如下：

```
<type>: <description>

[optional body]

[optional footer(s)]
```

### 类型（Type）

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档变更 |
| `test` | 添加或修改测试 |
| `refactor` | 代码重构（不改变功能） |
| `chore` | 构建、依赖等杂项 |
| `perf` | 性能优化 |
| `style` | 代码格式调整 |

### 示例

```
feat: 添加多站点路径规划功能
fix: 修复高德 API 超时时未正确重试的问题
docs: 更新 API 接口文档中的参数说明
test: 为 route_service 添加单元测试
refactor: 将 api.py 拆分为独立的服务层模块
```

## PR 流程

### 提交 Pull Request

1. **推送分支到远程**
   ```bash
   git push origin feat/your-feature-name
   ```

2. **创建 PR**
   - 在 GitHub 上点击 **New Pull Request**
   - 选择你的分支作为 source，`main` 作为 target
   - 使用 PR 模板填写描述

3. **PR 描述要求**
   - 清楚描述改动内容和原因
   - 关联相关 Issue（使用 `Closes #123` 语法）
   - 如有 UI 变更，附上截图

4. **通过 CI 检查**
   - 所有自动化测试必须通过
   - 代码检查（lint）必须通过
   - 至少需要一位维护者 Review

5. **响应 Review 反馈**
   - 及时回复评审意见
   - 按要求修改后推送更新

## 测试要求

### 基本要求

- **新增代码必须包含对应的测试**
- 修复 Bug 时需添加能复现该 Bug 的测试用例
- 所有测试必须通过才能合并

### 运行测试

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行测试并生成覆盖率报告
python -m pytest tests/ --cov=. --cov-report=term-missing --cov-report=html

# 运行指定测试文件
python -m pytest tests/test_route_service.py -v
```

### 测试规范

- 测试文件放在 `tests/` 目录下
- 文件名以 `test_` 开头
- 使用 `pytest` 框架
- 测试函数命名清晰，体现测试意图
- Mock 外部 API 调用，避免依赖网络

## 获取帮助

- 有问题可以在 Issue 中提问
- 查看 `docs/` 目录下的项目文档
- 查阅 README.md 了解项目概况

---

再次感谢你的贡献！每一份努力都让 SmartRoute 变得更好。
