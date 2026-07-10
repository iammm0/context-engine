import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Activity, Bot, CheckCircle2, Cpu, RefreshCw, RotateCcw, Save, Settings2, SlidersHorizontal } from "lucide-react"
import { useMemo, useRef, useState } from "react"

import { ArchitectureFlowPanel } from "@/components/settings/architecture-flow"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import type {
  AgentConfigItem,
  AgentConfigUpdate,
  MetricsResponse,
  RuntimeConfigResponse,
  RuntimeConfigUpdate,
} from "@/types/api"

type RuntimeMode = RuntimeConfigResponse["mode"]
type ParamInputType = "boolean" | "number" | "text"

type RuntimeDraft = {
  mode: RuntimeMode
  modules: Record<string, boolean>
  params: Record<string, string>
}

type AgentDraft = {
  enabled: boolean
  inference_model: string
  embedding_model: string
  system_prompt: string
}

type Feedback = {
  tone: "success" | "error" | "info"
  message: string
}

const runtimeModules = [
  ["kg_extract_enabled", "图谱构建", "入库阶段抽取三元组"],
  ["kg_retrieve_enabled", "图谱检索", "查询阶段启用图谱关联"],
  ["query_analyze_enabled", "查询分析", "判断是否需要检索增强"],
  ["query_rewrite_enabled", "查询改写", "为检索生成改写查询"],
  ["citation_check_enabled", "引用校验", "检查证据覆盖与引用有效性"],
  ["rerank_enabled", "重排", "启用 CrossEncoder 重排"],
  ["ocr_image_enabled", "图片 OCR", "解析图片和扫描件文本"],
  ["table_parse_enabled", "表格增强", "保留表格结构和来源定位"],
  ["legacy_deep_research_html_enabled", "深研 HTML", "保留旧版深度研究 HTML 输出"],
  ["embedding_enabled", "向量化", "基础能力，后端会强制开启"],
] as const

const runtimeParams = [
  ["retrieval_fusion_strategy", "检索融合策略", "text"],
  ["context_budget", "上下文预算", "number"],
  ["kg_concurrency", "图谱并发", "number"],
  ["kg_chunk_timeout_s", "图谱单块超时秒", "number"],
  ["kg_max_chunks", "图谱最大块数", "number"],
  ["embedding_batch_size", "向量化 batch", "number"],
  ["embedding_concurrency", "向量化并发", "number"],
  ["ocr_concurrency", "OCR 并发", "number"],
  ["http_log_level", "HTTP 日志级别", "text"],
  ["http_log_request_level", "请求日志级别", "text"],
  ["http_log_success_level", "成功日志级别", "text"],
  ["http_log_slow_level", "慢请求日志级别", "text"],
  ["http_log_client_error_level", "客户端错误级别", "text"],
  ["http_log_server_error_level", "服务端错误级别", "text"],
  ["http_log_slow_threshold_s", "慢请求阈值秒", "number"],
  ["http_log_success_enabled", "记录成功请求", "boolean"],
  ["http_log_include_query", "记录 query", "boolean"],
  ["http_log_include_client_ip", "记录 client IP", "boolean"],
  ["http_log_include_request_body", "记录请求体", "boolean"],
  ["http_log_request_body_max_chars", "请求体最大字符", "number"],
] as const satisfies readonly (readonly [string, string, ParamInputType])[]

const runtimeModeLabels: Record<RuntimeMode, string> = {
  low: "低配",
  high: "高配",
  custom: "自定义",
}

function buildRuntimeDraft(config?: RuntimeConfigResponse): RuntimeDraft {
  return {
    mode: config?.mode || "custom",
    modules: { ...(config?.modules || {}) },
    params: Object.fromEntries(Object.entries(config?.params || {}).map(([key, value]) => [key, String(value ?? "")])),
  }
}

function parseParam(raw: string, type: ParamInputType) {
  const value = raw.trim()
  if (value === "") {
    return undefined
  }
  if (type === "boolean") {
    return value === "true"
  }
  if (type === "number") {
    const numberValue = Number(value)
    return Number.isFinite(numberValue) ? numberValue : value
  }
  return value
}

function serializeParams(params: Record<string, string>) {
  const paramTypes = new Map<string, ParamInputType>(runtimeParams.map(([key, , type]) => [key, type]))
  return Object.fromEntries(
    Object.entries(params)
      .map(([key, value]) => [key, parseParam(value, paramTypes.get(key) || "text")] as const)
      .filter(([, value]) => value !== undefined),
  )
}

function paramFieldFor(key: string) {
  return runtimeParams.find(([itemKey]) => itemKey === key)
}

function agentDraftFrom(agent: AgentConfigItem): AgentDraft {
  return {
    enabled: agent.enabled,
    inference_model: agent.inference_model || "",
    embedding_model: agent.embedding_model || "",
    system_prompt: agent.system_prompt || "",
  }
}

function agentUpdateBody(agent: AgentConfigItem, draft: AgentDraft): AgentConfigUpdate {
  return {
    inference_model: draft.inference_model.trim(),
    embedding_model: draft.embedding_model.trim(),
    system_prompt: draft.system_prompt,
    enabled: agent.enable_locked ? true : draft.enabled,
    clear_system_prompt: false,
  }
}

function feedbackClass(tone: Feedback["tone"]) {
  if (tone === "success") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800"
  }
  if (tone === "error") {
    return "border-rose-200 bg-rose-50 text-rose-800"
  }
  return "border-sky-200 bg-sky-50 text-sky-800"
}

function statusBadgeClass(status?: string) {
  const normalized = (status || "").toLowerCase()
  if (["healthy", "ready", "alive"].includes(normalized)) {
    return "bg-emerald-100 text-emerald-800"
  }
  if (["degraded", "not_ready"].includes(normalized)) {
    return "bg-amber-100 text-amber-800"
  }
  if (normalized) {
    return "bg-rose-100 text-rose-800"
  }
  return "bg-slate-100 text-slate-600"
}

function formatServiceValue(value: unknown) {
  if (typeof value === "boolean") {
    return value ? "true" : "false"
  }
  if (typeof value === "number") {
    return String(value)
  }
  if (typeof value === "string") {
    return value || "空"
  }
  return undefined
}

function serviceDetailEntries(service: Record<string, unknown>) {
  return Object.entries(service)
    .filter(([key]) => !["status", "connected", "error"].includes(key))
    .map(([key, value]) => [key, formatServiceValue(value)] as const)
    .filter(([, value]) => value !== undefined)
}

function metricNumber(metrics: MetricsResponse | undefined, group: string, key: string) {
  const groupValue = metrics?.system_metrics?.[group]
  if (!groupValue || typeof groupValue !== "object") {
    return undefined
  }
  const value = (groupValue as Record<string, unknown>)[key]
  return typeof value === "number" ? value : undefined
}

function formatPercent(value?: number) {
  return typeof value === "number" ? `${Math.round(value)}%` : "未知"
}

function formatDate(value?: string | null) {
  if (!value) {
    return "尚未保存"
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}

export function SettingsLab() {
  const queryClient = useQueryClient()
  const [runtimeDraftOverride, setRuntimeDraftOverride] = useState<RuntimeDraft | null>(null)
  const [agentDraftOverrides, setAgentDraftOverrides] = useState<Record<string, AgentDraft>>({})
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const runtimeSectionRef = useRef<HTMLElement>(null)
  const healthSectionRef = useRef<HTMLElement>(null)
  const agentsSectionRef = useRef<HTMLElement>(null)

  const runtimeQuery = useQuery({
    queryKey: ["runtime-config"],
    queryFn: async () => {
      const result = await api.getRuntimeConfig()
      if (result.error || !result.data) {
        throw new Error(result.error || "运行时配置为空")
      }
      return result.data
    },
  })

  const agentsQuery = useQuery({
    queryKey: ["agent-configs"],
    queryFn: async () => {
      const result = await api.getAgents()
      if (result.error || !result.data) {
        throw new Error(result.error || "Agent 配置为空")
      }
      return result.data
    },
  })

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const result = await api.getModels()
      if (result.error) {
        throw new Error(result.error)
      }
      return result.data
    },
  })

  const healthQuery = useQuery({
    queryKey: ["backend-health"],
    queryFn: async () => {
      const result = await api.getHealth()
      if (result.error || !result.data) {
        throw new Error(result.error || "健康状态为空")
      }
      return result.data
    },
    refetchInterval: 30_000,
  })

  const readinessQuery = useQuery({
    queryKey: ["backend-readiness"],
    queryFn: async () => {
      const result = await api.getReadiness()
      if (result.error || !result.data) {
        throw new Error(result.error || "就绪状态为空")
      }
      return result.data
    },
    refetchInterval: 30_000,
  })

  const metricsQuery = useQuery({
    queryKey: ["backend-metrics"],
    queryFn: async () => {
      const result = await api.getMetrics()
      if (result.error || !result.data) {
        throw new Error(result.error || "指标为空")
      }
      return result.data
    },
    refetchInterval: 30_000,
  })

  const modelNames = useMemo(() => modelsQuery.data?.models?.map((model) => model.name) || [], [modelsQuery.data])
  const healthServices = useMemo(() => Object.entries(healthQuery.data?.services || {}), [healthQuery.data])
  const taskQueue = useMemo(() => {
    const service = healthQuery.data?.services?.task_queue
    return service && typeof service === "object" ? (service as Record<string, unknown>) : undefined
  }, [healthQuery.data])
  const activeAgentCount = useMemo(
    () => (agentsQuery.data?.agents || []).filter((agent) => agent.enabled).length,
    [agentsQuery.data],
  )
  const dirtyAgents = useMemo(
    () => (agentsQuery.data?.agents || []).filter((agent) => Boolean(agentDraftOverrides[agent.agent_type])),
    [agentDraftOverrides, agentsQuery.data],
  )
  const cpuPercent = metricNumber(metricsQuery.data, "cpu", "percent")
  const memoryPercent = metricNumber(metricsQuery.data, "memory", "percent")
  const diskPercent = metricNumber(metricsQuery.data, "disk", "percent")
  const runtimeBaseDraft = useMemo(() => buildRuntimeDraft(runtimeQuery.data), [runtimeQuery.data])
  const runtimeDraft = runtimeDraftOverride || runtimeBaseDraft

  const moduleRows = useMemo(() => {
    const known = runtimeModules.map(([key]) => key)
    const dynamic = Object.keys(runtimeDraft.modules).filter((key) => !known.includes(key as (typeof known)[number]))
    return [
      ...runtimeModules.map(([key, label, hint]) => ({ key, label, hint, locked: key === "embedding_enabled" })),
      ...dynamic.map((key) => ({ key, label: key, hint: "后端返回的扩展模块", locked: false })),
    ]
  }, [runtimeDraft.modules])

  const paramRows = useMemo(() => {
    const known = runtimeParams.map(([key]) => key)
    const dynamic = Object.keys(runtimeDraft.params).filter((key) => !known.includes(key as (typeof known)[number]))
    return [
      ...runtimeParams.map(([key, label, type]) => ({ key, label, type })),
      ...dynamic.map((key) => ({ key, label: key, type: "text" as const })),
    ]
  }, [runtimeDraft.params])

  const runtimeMutation = useMutation({
    mutationFn: async (body: RuntimeConfigUpdate) => {
      const result = await api.updateRuntimeConfig(body)
      if (result.error || !result.data) {
        throw new Error(result.error || "保存运行时配置失败")
      }
      return result.data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["runtime-config"], data)
      setRuntimeDraftOverride(null)
      setFeedback({ tone: "success", message: "运行时配置已保存" })
    },
    onError: (error) => {
      setFeedback({ tone: "error", message: error instanceof Error ? error.message : "保存运行时配置失败" })
    },
  })

  const agentMutation = useMutation({
    mutationFn: async ({ agentType, body }: { agentType: string; body: AgentConfigUpdate }) => {
      const result = await api.updateAgentConfig(agentType, body)
      if (result.error || !result.data) {
        throw new Error(result.error || "保存 Agent 配置失败")
      }
      return result.data
    },
    onSuccess: async (agent) => {
      setAgentDraftOverrides((current) => {
        const next = { ...current }
        delete next[agent.agent_type]
        return next
      })
      await queryClient.invalidateQueries({ queryKey: ["agent-configs"] })
      setFeedback({ tone: "success", message: `${agent.label} 已保存` })
    },
    onError: (error) => {
      setFeedback({ tone: "error", message: error instanceof Error ? error.message : "保存 Agent 配置失败" })
    },
  })

  const bulkAgentMutation = useMutation({
    mutationFn: async (agents: AgentConfigItem[]) => {
      const updates = agents.map((agent) => {
        const draft = agentDraftOverrides[agent.agent_type] || agentDraftFrom(agent)
        return api.updateAgentConfig(agent.agent_type, agentUpdateBody(agent, draft)).then((result) => {
          if (result.error || !result.data) {
            throw new Error(result.error || `${agent.label} 保存失败`)
          }
          return result.data
        })
      })
      return Promise.all(updates)
    },
    onSuccess: async (agents) => {
      const savedTypes = new Set(agents.map((agent) => agent.agent_type))
      setAgentDraftOverrides((current) => {
        const next = { ...current }
        for (const agentType of savedTypes) {
          delete next[agentType]
        }
        return next
      })
      await queryClient.invalidateQueries({ queryKey: ["agent-configs"] })
      setFeedback({ tone: "success", message: `已保存 ${agents.length} 个 Agent 配置` })
    },
    onError: (error) => {
      setFeedback({ tone: "error", message: error instanceof Error ? error.message : "批量保存 Agent 配置失败" })
    },
  })

  const requestErrors = [
    runtimeQuery.error instanceof Error ? `运行时配置加载失败：${runtimeQuery.error.message}` : null,
    agentsQuery.error instanceof Error ? `Agent 配置加载失败：${agentsQuery.error.message}` : null,
    modelsQuery.error instanceof Error ? `模型列表加载失败：${modelsQuery.error.message}` : null,
    healthQuery.error instanceof Error ? `健康状态加载失败：${healthQuery.error.message}` : null,
    readinessQuery.error instanceof Error ? `就绪状态加载失败：${readinessQuery.error.message}` : null,
    metricsQuery.error instanceof Error ? `指标加载失败：${metricsQuery.error.message}` : null,
  ].filter(Boolean) as string[]

  const navigateArchitectureTarget = (target: "runtime" | "agents" | "health", label: string) => {
    const targetRef =
      target === "runtime" ? runtimeSectionRef : target === "agents" ? agentsSectionRef : healthSectionRef

    targetRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
    setFeedback({ tone: "info", message: `已定位到 ${label}` })
  }

  const saveRuntime = () => {
    runtimeMutation.mutate({
      mode: "custom",
      modules: { ...runtimeDraft.modules, embedding_enabled: true },
      params: serializeParams(runtimeDraft.params),
    })
  }

  const applyPreset = (mode: Exclude<RuntimeMode, "custom">) => {
    runtimeMutation.mutate({ mode })
  }

  const updateAgentDraft = <K extends keyof AgentDraft>(agentType: string, key: K, value: AgentDraft[K]) => {
    const sourceAgent = agentsQuery.data?.agents.find((agent) => agent.agent_type === agentType)
    const baseDraft = sourceAgent ? agentDraftFrom(sourceAgent) : { enabled: true, inference_model: "", embedding_model: "", system_prompt: "" }
    setAgentDraftOverrides((current) => ({
      ...current,
      [agentType]: {
        ...(current[agentType] || baseDraft),
        [key]: value,
      },
    }))
  }

  const saveAgent = (agent: AgentConfigItem) => {
    const draft = agentDraftOverrides[agent.agent_type] || agentDraftFrom(agent)
    if (!draft) {
      return
    }
    agentMutation.mutate({
      agentType: agent.agent_type,
      body: agentUpdateBody(agent, draft),
    })
  }

  const saveAllAgents = () => {
    if (!dirtyAgents.length) {
      return
    }
    bulkAgentMutation.mutate(dirtyAgents)
  }

  const resetAgentPrompt = (agent: AgentConfigItem) => {
    const draft = agentDraftOverrides[agent.agent_type] || agentDraftFrom(agent)
    agentMutation.mutate({
      agentType: agent.agent_type,
      body: {
        inference_model: draft?.inference_model.trim() || "",
        embedding_model: draft?.embedding_model.trim() || "",
        enabled: agent.enable_locked ? true : draft?.enabled,
        clear_system_prompt: true,
      },
    })
  }

  return (
    <div className="grid gap-4">
      <ArchitectureFlowPanel
        activeAgentCount={activeAgentCount}
        modules={runtimeDraft.modules}
        onNavigate={navigateArchitectureTarget}
        taskQueue={taskQueue}
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <div className="grid gap-4">
          <section ref={runtimeSectionRef} className="scroll-mt-4">
            <Card>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <SlidersHorizontal className="size-5 text-sky-700" />
                  运行时配置
                </CardTitle>
                <CardDescription>当前模式：{runtimeModeLabels[runtimeDraft.mode]}</CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge>{formatDate(runtimeQuery.data?.updated_at)}</Badge>
                <Button
                  disabled={runtimeQuery.isFetching}
                  onClick={() => void runtimeQuery.refetch()}
                  size="sm"
                  variant="outline"
                >
                  <RefreshCw className="size-3.5" />
                  刷新
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-2 sm:grid-cols-3">
              <Button disabled={runtimeMutation.isPending} onClick={() => applyPreset("low")} variant="secondary">
                低配
              </Button>
              <Button disabled={runtimeMutation.isPending} onClick={() => applyPreset("high")} variant="secondary">
                高配
              </Button>
              <Button disabled={runtimeMutation.isPending} onClick={saveRuntime}>
                <Save className="size-4" />
                保存自定义
              </Button>
            </div>

            <section className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                <Settings2 className="size-4 text-sky-700" />
                模块开关
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                {moduleRows.map((item) => (
                  <label
                    className="flex min-w-0 items-start justify-between gap-3 rounded-lg border border-[var(--blue-line)] bg-white px-3 py-2"
                    key={item.key}
                  >
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-slate-900">{item.label}</span>
                      <span className="block text-xs leading-5 text-slate-500">{item.hint}</span>
                    </span>
                    <input
                      checked={item.locked ? true : Boolean(runtimeDraft.modules[item.key])}
                      className="mt-1 size-4 shrink-0 accent-sky-700"
                        disabled={item.locked || runtimeMutation.isPending}
                        onChange={(event) =>
                        setRuntimeDraftOverride((current) => {
                          const source = current || runtimeDraft
                          return {
                            ...source,
                            mode: "custom",
                            modules: { ...source.modules, [item.key]: event.target.checked },
                          }
                        })
                      }
                      type="checkbox"
                    />
                  </label>
                ))}
              </div>
            </section>

            <section className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                <Cpu className="size-4 text-sky-700" />
                参数
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {paramRows.map((item) => {
                  const configuredField = paramFieldFor(item.key)
                  const inputType = configuredField?.[2] || item.type
                  const value = runtimeDraft.params[item.key] ?? ""
                  return (
                    <label className="grid min-w-0 gap-1.5" key={item.key}>
                      <span className="text-xs font-medium text-slate-600">{item.label}</span>
                      {inputType === "boolean" ? (
                        <select
                          className="h-11 rounded-xl border border-[var(--blue-line)] bg-white px-3 text-sm text-slate-950 outline-none focus-visible:border-sky-400 focus-visible:ring-4 focus-visible:ring-sky-100"
                          disabled={runtimeMutation.isPending}
                          onChange={(event) =>
                            setRuntimeDraftOverride((current) => {
                              const source = current || runtimeDraft
                              return {
                                ...source,
                                mode: "custom",
                                params: { ...source.params, [item.key]: event.target.value },
                              }
                            })
                          }
                          value={value === "true" ? "true" : "false"}
                        >
                          <option value="true">开启</option>
                          <option value="false">关闭</option>
                        </select>
                      ) : (
                        <Input
                          disabled={runtimeMutation.isPending}
                          inputMode={inputType === "number" ? "decimal" : undefined}
                          onChange={(event) =>
                            setRuntimeDraftOverride((current) => {
                              const source = current || runtimeDraft
                              return {
                                ...source,
                                mode: "custom",
                                params: { ...source.params, [item.key]: event.target.value },
                              }
                            })
                          }
                          placeholder="默认"
                          value={value}
                        />
                      )}
                    </label>
                  )
                })}
              </div>
            </section>
          </CardContent>
            </Card>
          </section>

          <section ref={healthSectionRef} className="scroll-mt-4">
            <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="size-5 text-emerald-700" />
              状态
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {feedback ? (
              <div className={`rounded-lg border px-3 py-2 text-sm ${feedbackClass(feedback.tone)}`}>
                {feedback.message}
              </div>
            ) : null}
            {requestErrors.length > 0 ? (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
                {requestErrors.map((error) => (
                  <div key={error}>{error}</div>
                ))}
              </div>
            ) : null}
            <div className="grid gap-2 text-sm text-slate-600 sm:grid-cols-3">
              <div className="rounded-lg border border-[var(--blue-line)] bg-white px-3 py-2">
                <div className="text-xs text-slate-500">模型</div>
                <div className="font-medium text-slate-900">{modelNames.length}</div>
              </div>
              <div className="rounded-lg border border-[var(--blue-line)] bg-white px-3 py-2">
                <div className="text-xs text-slate-500">Agent</div>
                <div className="font-medium text-slate-900">{agentsQuery.data?.agents?.length || 0}</div>
              </div>
              <div className="rounded-lg border border-[var(--blue-line)] bg-white px-3 py-2">
                <div className="text-xs text-slate-500">模式</div>
                <div className="font-medium text-slate-900">{runtimeModeLabels[runtimeDraft.mode]}</div>
              </div>
            </div>
            <section className="space-y-3 rounded-lg border border-[var(--blue-line)] bg-white p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                  <Activity className="size-4 text-emerald-700" />
                  后端健康
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge className={statusBadgeClass(healthQuery.data?.status)}>
                    {healthQuery.data?.status || "loading"}
                  </Badge>
                  <Badge className={statusBadgeClass(readinessQuery.data?.status)}>
                    {readinessQuery.data?.status || "unknown"}
                  </Badge>
                </div>
              </div>

              <div className="grid gap-2 text-sm sm:grid-cols-3">
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-xs text-slate-500">CPU</div>
                  <div className="font-medium text-slate-900">{formatPercent(cpuPercent)}</div>
                </div>
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-xs text-slate-500">内存</div>
                  <div className="font-medium text-slate-900">{formatPercent(memoryPercent)}</div>
                </div>
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-xs text-slate-500">磁盘</div>
                  <div className="font-medium text-slate-900">{formatPercent(diskPercent)}</div>
                </div>
              </div>

              {healthServices.length > 0 ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  {healthServices.map(([name, value]) => {
                    const service = value && typeof value === "object" ? (value as Record<string, unknown>) : {}
                    const status = typeof service.status === "string" ? service.status : "unknown"
                    const connected = typeof service.connected === "boolean" ? service.connected : undefined
                    const error = typeof service.error === "string" ? service.error : ""
                    const details = serviceDetailEntries(service)
                    return (
                      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs" key={name}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium text-slate-800">{name}</span>
                          <Badge className={statusBadgeClass(status)}>{status}</Badge>
                        </div>
                        <div className="mt-1 text-slate-500">
                          {connected === undefined ? "连接状态未知" : connected ? "已连接" : "未连接"}
                        </div>
                        {details.length > 0 ? (
                          <div className="mt-2 grid gap-1 text-slate-500">
                            {details.map(([key, value]) => (
                              <div className="flex min-w-0 justify-between gap-2" key={key}>
                                <span className="shrink-0">{key}</span>
                                <span className="min-w-0 truncate text-right text-slate-700">{value}</span>
                              </div>
                            ))}
                          </div>
                        ) : null}
                        {error ? <div className="mt-1 line-clamp-2 text-rose-700">{error}</div> : null}
                      </div>
                    )
                  })}
                </div>
              ) : null}
            </section>
          </CardContent>
            </Card>
          </section>
        </div>

        <section ref={agentsSectionRef} className="scroll-mt-4">
          <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Bot className="size-5 text-sky-700" />
                多 Agent 配置
              </CardTitle>
              <CardDescription>
                推理模型、向量模型、启用状态和系统提示词覆盖。
                {dirtyAgents.length > 0 ? ` 未保存 ${dirtyAgents.length} 项。` : ""}
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                disabled={bulkAgentMutation.isPending || agentMutation.isPending || dirtyAgents.length === 0}
                onClick={saveAllAgents}
                size="sm"
              >
                <Save className="size-3.5" />
                保存全部
              </Button>
              <Button
                disabled={agentsQuery.isFetching}
                onClick={() => void agentsQuery.refetch()}
                size="sm"
                variant="outline"
              >
                <RefreshCw className="size-3.5" />
                刷新
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {(agentsQuery.data?.agents || []).map((agent) => {
              const draft = agentDraftOverrides[agent.agent_type] || agentDraftFrom(agent)
              return (
                <section
                  className="rounded-lg border border-[var(--blue-line)] bg-white p-4"
                  key={agent.agent_type}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-sm font-semibold text-slate-950">{agent.label}</h4>
                        <Badge className="bg-white text-slate-700">{agent.role}</Badge>
                        <Badge className={draft.enabled ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"}>
                          {draft.enabled ? "启用" : "停用"}
                        </Badge>
                      </div>
                      <div className="mt-1 text-xs text-slate-500">{agent.agent_type}</div>
                    </div>
                    <label className="flex items-center gap-2 text-xs text-slate-600">
                      <span>启用</span>
                      <input
                        checked={agent.enable_locked ? true : draft.enabled}
                        className="size-4 accent-sky-700"
                        disabled={agent.enable_locked || agentMutation.isPending || bulkAgentMutation.isPending}
                        onChange={(event) => updateAgentDraft(agent.agent_type, "enabled", event.target.checked)}
                        type="checkbox"
                      />
                    </label>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <label className="grid gap-1.5">
                      <span className="text-xs font-medium text-slate-600">推理模型</span>
                      <Input
                        disabled={agentMutation.isPending || bulkAgentMutation.isPending}
                        list={`models-${agent.agent_type}`}
                        onChange={(event) => updateAgentDraft(agent.agent_type, "inference_model", event.target.value)}
                        placeholder="留空使用默认模型"
                        value={draft.inference_model}
                      />
                      <datalist id={`models-${agent.agent_type}`}>
                        {modelNames.map((name) => (
                          <option key={`${agent.agent_type}-${name}`} value={name} />
                        ))}
                      </datalist>
                    </label>
                    <label className="grid gap-1.5">
                      <span className="text-xs font-medium text-slate-600">向量模型</span>
                      <Input
                        disabled={agentMutation.isPending || bulkAgentMutation.isPending}
                        list={`embeddings-${agent.agent_type}`}
                        onChange={(event) => updateAgentDraft(agent.agent_type, "embedding_model", event.target.value)}
                        placeholder="通常留空"
                        value={draft.embedding_model}
                      />
                      <datalist id={`embeddings-${agent.agent_type}`}>
                        {modelNames.map((name) => (
                          <option key={`${agent.agent_type}-embedding-${name}`} value={name} />
                        ))}
                      </datalist>
                    </label>
                  </div>

                  <label className="mt-3 grid gap-1.5">
                    <span className="text-xs font-medium text-slate-600">系统提示词覆盖</span>
                    <Textarea
                      className="min-h-[132px] font-mono text-xs leading-5"
                      disabled={agentMutation.isPending || bulkAgentMutation.isPending}
                      onChange={(event) => updateAgentDraft(agent.agent_type, "system_prompt", event.target.value)}
                      placeholder="留空使用内置提示词"
                      value={draft.system_prompt}
                    />
                  </label>

                  <details className="mt-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                    <summary className="cursor-pointer font-medium text-slate-700">内置提示词</summary>
                    <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap leading-5">
                      {agent.builtin_system_prompt || "无"}
                    </pre>
                  </details>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      disabled={agentMutation.isPending || bulkAgentMutation.isPending}
                      onClick={() => saveAgent(agent)}
                      size="sm"
                    >
                      <Save className="size-3.5" />
                      保存
                    </Button>
                    <Button
                      disabled={agentMutation.isPending || bulkAgentMutation.isPending}
                      onClick={() => resetAgentPrompt(agent)}
                      size="sm"
                      variant="secondary"
                    >
                      <RotateCcw className="size-3.5" />
                      恢复内置提示词
                    </Button>
                  </div>
                </section>
              )
            })}
          </div>
          </CardContent>
        </Card>
      </section>
    </div>
    </div>
  )
}
