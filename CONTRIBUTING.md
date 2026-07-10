# 贡献指南

感谢你对 **context-engine** 的关注！我们欢迎任何形式的贡献，包括 Bug 报告、功能建议、文档改进和代码提交。

## 目录

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
- [开发环境搭建](#开发环境搭建)
- [提交规范](#提交规范)
- [Pull Request 流程](#pull-request-流程)
- [Issue 规范](#issue-规范)

---

## 行为准则

参与本项目即表示你同意遵守我们的 [行为准则](CODE_OF_CONDUCT.md)。

---

## 如何贡献

### 报告 Bug

1. 先搜索 [Issues](../../issues)，确认该 Bug 尚未被报告。
2. 点击 **New Issue**，选择 **Bug Report** 模板。
3. 填写完整的复现步骤、预期行为和实际行为。
4. 提供运行环境信息（OS、Python 版本、依赖版本等）。

### 提交功能建议

1. 先搜索 [Issues](../../issues)，确认该功能尚未被建议。
2. 点击 **New Issue**，选择 **Feature Request** 模板。
3. 描述功能的使用场景和预期效果。

### 贡献代码

1. Fork 本仓库。
2. 创建功能分支（见 [提交规范](#提交规范)）。
3. 完成开发并通过测试。
4. 提交 Pull Request。

---

## 开发环境搭建

### 前置条件

- Python 3.10+
- Node.js 18+（前端开发）
- MongoDB 4.4+
- Qdrant（向量数据库）
- Ollama（本地模型服务）

### 后端

```bash
# 克隆仓库
git clone https://github.com/iammm0/advanced-rag.git context-engine
cd context-engine

# 安装 Python 依赖
pip install -r requirements.txt

# 复制环境变量模板
cp .env.example .env
# 编辑 .env，填写必要配置

# 启动开发服务器
python main.py
```

### 前端

```bash
cd web

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

---

## 提交规范

### 分支命名

| 类型 | 格式 | 示例 |
|------|------|------|
| 新功能 | `feat/<描述>` | `feat/streaming-response` |
| Bug 修复 | `fix/<描述>` | `fix/qdrant-connection-error` |
| 文档 | `docs/<描述>` | `docs/update-api-docs` |
| 重构 | `refactor/<描述>` | `refactor/chunking-module` |
| 性能优化 | `perf/<描述>` | `perf/embedding-cache` |
| 测试 | `test/<描述>` | `test/add-agent-tests` |

### Commit Message 规范

采用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**type 类型：**

- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档变更
- `style`: 代码格式（不影响功能）
- `refactor`: 代码重构
- `perf`: 性能优化
- `test`: 添加/修改测试
- `chore`: 构建过程或辅助工具变更
- `ci`: CI/CD 配置变更

**示例：**

```
feat(agents): add deep-research streaming support

Add streaming SSE output for deep-research agent workflow.
Fixes #42
```

---

## Pull Request 流程

1. **确保** 你的分支基于最新的 `main` 分支。
2. **确保** 代码通过本地测试：
   ```bash
   python test_agent_workflow.py
   ```
3. **填写** PR 描述，说明改动内容、原因和测试方式。
4. **关联** 相关 Issue（如 `Closes #123`）。
5. 等待 Code Review，根据反馈进行修改。
6. 至少获得 **1 个 Approve** 后方可合并。

### PR 检查清单

- [ ] 代码遵循项目风格（Python 使用 PEP 8）
- [ ] 新功能已添加对应测试
- [ ] 文档已同步更新
- [ ] Commit Message 符合规范
- [ ] 没有引入不必要的依赖

---

## Issue 规范

- 使用中文或英文均可
- 标题简洁明了，说明问题或需求
- 提供足够的上下文信息
- Bug 报告请附上错误日志和复现步骤

---

如有疑问，欢迎在 [Discussions](../../discussions) 中提问。
