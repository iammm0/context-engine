import { Activity, Bot, BrainCircuit, Cpu, Database, FileSearch, GitBranch, Network, Workflow } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

type ArchitectureTarget = "runtime" | "agents" | "health"

type ArchitectureNode = {
  id: string
  label: string
  detail: string
  target: ArchitectureTarget
  moduleKey?: string
  agentType?: string
  tone?: "default" | "accent" | "muted"
}

type ArchitectureLane = {
  title: string
  icon: typeof Database
  nodes: ArchitectureNode[]
}

type ArchitectureFlowPanelProps = {
  modules: Record<string, boolean>
  activeAgentCount: number
  taskQueue?: Record<string, unknown>
  onNavigate: (target: ArchitectureTarget, label: string) => void
}

const lanes: ArchitectureLane[] = [
  {
    title: "入库链路",
    icon: Database,
    nodes: [
      {
        id: "upload",
        label: "文档与附件",
        detail: "上传后投递长任务",
        target: "health",
        tone: "accent",
      },
      {
        id: "ocr",
        label: "OCR",
        detail: "图片与扫描件文本",
        target: "runtime",
        moduleKey: "ocr_image_enabled",
      },
      {
        id: "table",
        label: "表格增强",
        detail: "结构与来源定位",
        target: "runtime",
        moduleKey: "table_parse_enabled",
      },
      {
        id: "kg_extract",
        label: "图谱构建",
        detail: "入库三元组抽取",
        target: "runtime",
        moduleKey: "kg_extract_enabled",
      },
    ],
  },
  {
    title: "检索链路",
    icon: FileSearch,
    nodes: [
      {
        id: "query_analyze",
        label: "查询分析",
        detail: "判断是否需要检索",
        target: "runtime",
        moduleKey: "query_analyze_enabled",
      },
      {
        id: "query_rewrite",
        label: "查询改写",
        detail: "生成检索查询",
        target: "runtime",
        moduleKey: "query_rewrite_enabled",
      },
      {
        id: "kg_retrieve",
        label: "图谱检索",
        detail: "查询阶段关系扩展",
        target: "runtime",
        moduleKey: "kg_retrieve_enabled",
      },
      {
        id: "rerank",
        label: "重排",
        detail: "CrossEncoder 精排",
        target: "runtime",
        moduleKey: "rerank_enabled",
      },
    ],
  },
  {
    title: "生成与深研",
    icon: BrainCircuit,
    nodes: [
      {
        id: "citation",
        label: "引用校验",
        detail: "证据覆盖与有效性",
        target: "runtime",
        moduleKey: "citation_check_enabled",
      },
      {
        id: "deep_research",
        label: "深度研究",
        detail: "协调器与专家 Agent",
        target: "agents",
        tone: "accent",
      },
      {
        id: "coordinator",
        label: "协调 Agent",
        detail: "任务拆分与汇总",
        target: "agents",
        agentType: "coordinator",
      },
      {
        id: "experts",
        label: "专家 Agent",
        detail: "公式、代码、文档等专家",
        target: "agents",
        tone: "muted",
      },
    ],
  },
  {
    title: "运行状态",
    icon: Activity,
    nodes: [
      {
        id: "task_queue",
        label: "任务队列",
        detail: "Celery / 本地后台",
        target: "health",
        tone: "accent",
      },
      {
        id: "vector_store",
        label: "向量库",
        detail: "Qdrant 连接状态",
        target: "health",
      },
      {
        id: "mongo",
        label: "元数据",
        detail: "MongoDB 连接状态",
        target: "health",
      },
      {
        id: "metrics",
        label: "系统指标",
        detail: "CPU / 内存 / 磁盘",
        target: "health",
        tone: "muted",
      },
    ],
  },
]

function moduleStatus(modules: Record<string, boolean>, node: ArchitectureNode) {
  if (!node.moduleKey) {
    return null
  }
  return modules[node.moduleKey] ? "on" : "off"
}

function taskQueueLabel(taskQueue?: Record<string, unknown>) {
  const backend = typeof taskQueue?.active_backend === "string" ? taskQueue.active_backend : undefined
  const workerCount = typeof taskQueue?.worker_count === "number" ? taskQueue.worker_count : undefined
  if (!backend) {
    return "unknown"
  }
  if (backend === "celery" && typeof workerCount === "number") {
    return `${backend} / ${workerCount}`
  }
  return backend
}

function nodeToneClass(node: ArchitectureNode) {
  if (node.tone === "accent") {
    return "border-sky-300 bg-sky-50 text-sky-950 hover:border-sky-400 hover:bg-sky-100"
  }
  if (node.tone === "muted") {
    return "border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-300 hover:bg-white"
  }
  return "border-[var(--blue-line)] bg-white text-slate-800 hover:border-sky-300 hover:bg-[var(--surface-blue)]"
}

export function ArchitectureFlowPanel({
  modules,
  activeAgentCount,
  taskQueue,
  onNavigate,
}: ArchitectureFlowPanelProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Workflow className="size-5 text-sky-700" />
              系统架构
            </CardTitle>
            <CardDescription>上下文引擎的入库、检索、生成和运行状态视图。</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge className="bg-white text-slate-700">{activeAgentCount} agents</Badge>
            <Badge className="bg-white text-slate-700">{taskQueueLabel(taskQueue)}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 lg:grid-cols-4">
          {lanes.map((lane, laneIndex) => {
            const LaneIcon = lane.icon
            return (
              <section className="min-w-0 rounded-lg border border-[var(--blue-line)] bg-slate-50/70 p-3" key={lane.title}>
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-950">
                  <LaneIcon className="size-4 text-sky-700" />
                  {lane.title}
                </div>
                <div className="space-y-2">
                  {lane.nodes.map((node, nodeIndex) => {
                    const status = moduleStatus(modules, node)
                    return (
                      <div className="relative" key={node.id}>
                        <Button
                          className={cn(
                            "h-auto min-h-[76px] w-full flex-col items-start gap-1 rounded-lg border px-3 py-2 text-left shadow-none",
                            nodeToneClass(node),
                          )}
                          onClick={() => onNavigate(node.target, node.label)}
                          type="button"
                          variant="ghost"
                        >
                          <span className="flex w-full items-center justify-between gap-2">
                            <span className="font-semibold">{node.label}</span>
                            {status ? (
                              <span
                                className={cn(
                                  "rounded-full px-2 py-0.5 text-[11px]",
                                  status === "on" ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-600",
                                )}
                              >
                                {status}
                              </span>
                            ) : null}
                          </span>
                          <span className="text-xs leading-5 text-slate-500">{node.detail}</span>
                        </Button>
                        {nodeIndex < lane.nodes.length - 1 ? (
                          <div className="mx-auto h-3 w-px bg-sky-200" aria-hidden="true" />
                        ) : null}
                      </div>
                    )
                  })}
                </div>
                {laneIndex < lanes.length - 1 ? (
                  <div className="mt-3 hidden items-center justify-end gap-1 text-xs text-slate-400 lg:flex">
                    <GitBranch className="size-3" />
                    <span>next</span>
                  </div>
                ) : null}
              </section>
            )
          })}
        </div>
        <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-3">
          <div className="flex items-center gap-2 rounded-lg bg-white px-3 py-2">
            <Cpu className="size-3.5 text-sky-700" />
            <span>运行时开关由后端配置持久化。</span>
          </div>
          <div className="flex items-center gap-2 rounded-lg bg-white px-3 py-2">
            <Bot className="size-3.5 text-sky-700" />
            <span>深研专家复用 Agent 配置。</span>
          </div>
          <div className="flex items-center gap-2 rounded-lg bg-white px-3 py-2">
            <Network className="size-3.5 text-sky-700" />
            <span>任务队列状态来自健康接口。</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
