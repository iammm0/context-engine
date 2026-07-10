# advanced-rag TanStack Frontend

这是一套并列于现有 `web/` Next.js 前端的新实现，目录为 `web-tanstack/`。  
目标是基于你指定的技术栈，落一套可运行、可继续扩展、并且已经接上现有 FastAPI 后端的 TanStack 系列前端骨架。

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
- Monaco Editor
- xterm.js
- React Flow

## 当前已完成

- 搭建了独立应用入口与路由骨架
- 接入了现有后端 API：
  - `GET /api/chat/models`
  - `GET /api/chat/conversations`
  - `GET /api/chat/conversations/{id}`
  - `POST /api/chat/conversations`
  - `POST /api/chat/conversations/{id}/messages`
  - `POST /api/chat`
  - `GET /api/knowledge-spaces`
  - `POST /api/knowledge-spaces`
  - `GET /api/documents`
  - `POST /api/documents/upload`
  - `GET /api/documents/{id}/progress/stream`
  - `GET /api/settings/runtime`
  - `GET /api/settings/agents`
- 通过 `npm run generate:api` 从 FastAPI OpenAPI schema 生成 `src/types/generated-api.ts`
- 做了 3 个主页面：
  - `Chat`：SSE 流式聊天、会话列表、RAG 开关
  - `Documents`：知识空间列表、上传入口、TanStack Table + Virtual 文档表格、文档处理进度 SSE 订阅
  - `Settings`：React Flow 架构图、Monaco 配置编辑器、xterm.js 终端面板
- 完成 `shadcn/ui` 初始化和 `components.json`
- 已通过 `npm run build` 和 `npm run lint`

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

- 把 `Monaco` 编辑器扩展成运行时配置编辑面板，支持保存回 `/api/settings/runtime`
- 把聊天页补齐深度研究模式与 Agent 状态流
- 把大体积依赖做路由级懒加载，优先拆 `Monaco`、`xterm.js`、`React Flow`
- 继续补齐更多 shadcn 组件，例如 `dialog`、`sheet`、`dropdown-menu`、`tabs`

## 说明

当前仓库里原有的 `web/` Next.js 前端没有被替换，这个 `web-tanstack/` 是一套新的并列实现，适合你继续沿 TanStack 系列往下演进。
