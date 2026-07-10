# 前端应用模块（context-engine-web）

`context-engine` 的 Next.js 前端应用，提供用户交互界面（**匿名访问**）。仅保留 **聊天（含深度研究）** 与 **知识空间上传/列表**。

## 功能特性

- **聊天界面**：实时聊天，支持流式文本显示、对话历史侧边栏
- **深度研究**：多 Agent 协作输出深度研究内容
- **知识库**：上传文档入库、列表/进度展示，聊天中可开启 RAG 检索增强并显示 sources
- **响应式设计**：支持移动端和桌面端

## 技术栈

- Next.js 16
- React 19
- TypeScript
- Tailwind CSS

## 安装依赖

```bash
npm install
```

## 开发

```bash
npm run dev
```

访问 `http://localhost:3000`

## 构建

```bash
npm run build
npm start
```

## 环境配置

创建 `.env.local` 文件：

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

如果不设置 `NEXT_PUBLIC_API_URL`，前端默认使用 `http://localhost:8000` 作为后端地址。

## 页面说明

### 聊天页面 (`/chat`)

- 匿名访问
- 支持选择 AI 助手
- 支持基于知识空间的 RAG 检索增强
- 支持流式和非流式回复
- 支持深度研究模式

### 知识空间页面 (`/documents`)

- 上传文档到指定知识空间
- 查看文档列表和处理进度
- 管理文档（删除、重新处理）

## 目录结构（简要）

```
web/
├── app/                # Next.js App Router 页面
│   ├── chat/           # 聊天页面
│   ├── documents/      # 知识空间页面
│   ├── layout.tsx      # 根布局与元数据
│   └── globals.css     # 全局样式
├── components/         # React 组件
│   ├── chat/           # 聊天相关组件
│   └── ui/             # 通用 UI 组件（导航栏等）
├── lib/                # 前端工具函数
└── public/             # 静态资源（包含 favicon 等）
```

## 主要功能说明

### 聊天功能

- 支持选择不同的 AI 助手进行对话
- 支持流式和非流式回复
- 支持基于知识空间的 RAG 检索
- 支持深度研究模式，多 Agent 协作生成长文研究结果

### 知识空间管理

- 上传常见格式文档（PDF/Word/Markdown/TXT）
- 查看入库进度和处理状态
- 失败文档可重新处理
