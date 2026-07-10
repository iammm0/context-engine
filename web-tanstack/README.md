# context-engine TanStack Frontend

`web-tanstack/` 是 `context-engine` 后续主前端。旧 `web/` Next.js 前端仅作为历史兼容和功能平移参照保留，新功能优先在这里实现和验证。

目标是基于 Vite + TanStack 系列维护一套可运行、可继续扩展、并且与现有 FastAPI 后端 OpenAPI 契约同步的主前端。

## 技术栈

- React 19
- Vite 8
- TypeScript 6
- TanStack Router
- TanStack Query
- TanStack Table
- TanStack Virtual
- Tailwind CSS v4
- shadcn/ui
- Zustand

## 当前已完成

- 搭建了独立应用入口与路由骨架
- 接入了现有后端 API：
  - `GET /api/chat/models`
  - `GET /api/chat/conversations`
  - `GET /api/chat/conversations/{id}`
  - `POST /api/chat/conversations`
  - `POST /api/chat/conversations/{id}/messages`
  - `POST /api/chat`
  - `POST /api/chat/deep-research/task`
  - `GET /api/tasks/{id}/stream`
  - `GET /api/knowledge-spaces`
  - `POST /api/knowledge-spaces`
  - `GET /api/documents`
  - `POST /api/documents/upload`
  - `GET /api/documents/{id}/progress/stream`
  - `GET /api/settings/runtime`
  - `GET /api/settings/agents`
- 通过 `npm run generate:api` 从 FastAPI OpenAPI schema 生成 `src/types/generated-api.ts`
- 通过 `npm run check:api` 检查 generated API types 是否和后端 OpenAPI schema 同步
- 做了 3 个主页面：
  - `Chat`：SSE 流式聊天、会话列表、RAG 开关、深度研究 Celery 任务投递与任务 SSE 进度订阅
  - `Documents`：知识空间列表、上传入口、TanStack Table + Virtual 文档表格、文档处理进度 SSE 订阅、chunk 深链定位和质量筛选
  - `Settings`：运行时配置、Agent 配置、后端健康状态和系统架构视图
- 完成 `shadcn/ui` 初始化和 `components.json`
- 已通过 `npm run verify`

## 启动方式

先确保后端服务运行在 `http://localhost:8000`。

```bash
cd web-tanstack
npm install
npm run generate:api
npm run dev
```

默认访问：

```txt
http://localhost:5173
```

## 环境变量

可选创建 `.env.local` 或 `.env`：

```bash
VITE_API_URL=http://localhost:8000
```

如果不设置，默认就是 `http://localhost:8000`。

## 验证

后端 API schema 变化后先重新生成类型：

```bash
npm run generate:api
```

提交前运行完整前端验证：

```bash
npm run verify
```

`verify` 会检查当前 `src/types/generated-api.ts` 是否和 FastAPI OpenAPI schema 同步，然后依次运行 lint、TypeScript 类型检查和生产构建。如果只想确认 generated types 没有漂移，可以单独运行：

```bash
npm run check:api
```

## 目录说明

```txt
web-tanstack/
├── src/
│   ├── components/
│   │   ├── chat/
│   │   ├── documents/
│   │   ├── settings/
│   │   ├── shell/
│   │   └── ui/
│   ├── lib/
│   ├── stores/
│   ├── types/
│   ├── index.css
│   ├── main.tsx
│   └── router.tsx
├── components.json
└── vite.config.ts
```

## 后续建议

- 继续从旧 `web/` 平移仍有价值的聊天辅助体验，避免在旧前端继续新增功能。
- 将更多长任务统一接入 `POST task + /api/tasks/{id}/stream` 的模式。
- 保持 `npm run generate:api` 和 `npm run check:api` 作为 API 类型同步的提交前检查。
- 继续补齐更多 shadcn 组件，例如 `dialog`、`sheet`、`dropdown-menu`、`tabs`。

## 说明

当前仓库里原有的 `web/` Next.js 前端还没有物理删除，但 `web-tanstack/` 是后续主前端；迁移或新增功能时应优先修改本目录。
