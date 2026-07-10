import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Bot,
  BrainCircuit,
  Check,
  Cpu,
  FileSearch,
  Paperclip,
  Pencil,
  RotateCcw,
  SendHorizontal,
  Sparkles,
  Trash2,
  UploadCloud,
  User,
  X,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import {
  ArtifactSourceLocatorPreview,
  SourceLocatorAnchorPreview,
} from "@/components/evidence/source-locator-preview"
import { formatSourceLocatorSummary } from "@/components/evidence/source-locator-utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { useUiStore } from "@/stores/ui-store"
import type {
  ChatStreamEvent,
  ConversationAttachmentStatus,
  CitationEvidenceAudit,
  CitationEvidenceRef,
  CitationQuality,
  ConversationDetail,
  ConversationMessage,
  DeepResearchAgentResult,
  DeepResearchAgentStatus,
  DeepResearchEvaluation,
  DeepResearchStreamEvent,
  EvidenceItem,
  EvidenceQuality,
  TaskDispatchInfo,
} from "@/types/api"

type ChatAttachment = {
  file_id: string
  conversation_id: string
  document_id?: string
  filename: string
  status: string
  progress_percentage?: number | null
  current_stage?: string | null
  stage_details?: string | null
  message?: string | null
  task?: TaskDispatchInfo | null
  error?: string
}

function formatTime(value?: string | null) {
  if (!value) {
    return "刚刚"
  }

  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}

function isAttachmentProcessing(status?: string | null) {
  if (!status) {
    return true
  }
  return !["completed", "failed", "cancelled"].includes(status)
}

function taskBackendLabel(task?: TaskDispatchInfo | null) {
  if (!task?.backend) {
    return null
  }
  if (task.backend === "celery") {
    return "Celery"
  }
  if (task.backend === "fastapi-background") {
    return "Local"
  }
  return task.backend
}

function taskSummary(task?: TaskDispatchInfo | null) {
  const label = taskBackendLabel(task)
  if (!label) {
    return null
  }
  if (task?.task_id) {
    return `${label} #${task.task_id.slice(0, 8)}`
  }
  return label
}

function mergeAttachmentStatus(current: ChatAttachment, status: ConversationAttachmentStatus): ChatAttachment {
  return {
    ...current,
    filename: status.filename || current.filename,
    document_id: status.document_id ?? current.document_id,
    status: status.status || current.status,
    progress_percentage: status.progress_percentage ?? current.progress_percentage,
    current_stage: status.current_stage,
    stage_details: status.stage_details,
    message: status.message,
    task: status.task ?? current.task,
  }
}

const evidenceTypeLabel: Record<string, string> = {
  text: "文本",
  table: "表格",
  image_ocr: "图片OCR",
  ocr: "OCR",
  formula: "公式",
  code: "代码",
  graph: "图谱",
}

const citationRiskReasonLabel: Record<string, string> = {
  missing_source_locator: "缺来源定位",
  artifact_warning: "解析需复核",
  low_confidence_ocr: "低置信OCR",
  quality_note: "质量提示",
}

const deepResearchAgentLabels: Record<string, string> = {
  coordinator: "协调规划",
  document_retrieval: "文档检索",
  argument_analysis: "论证分析",
  concept_explanation: "概念解释",
  critic: "批判审阅",
  summary: "总结整合",
  formula_analysis: "公式分析",
  code_analysis: "代码分析",
  example_generation: "示例生成",
  exercise: "练习设计",
  scientific_coding: "科学计算",
}

const DEFAULT_DEEP_RESEARCH_AGENTS = [
  "coordinator",
  "document_retrieval",
  "argument_analysis",
  "concept_explanation",
  "critic",
  "summary",
  "formula_analysis",
  "code_analysis",
  "example_generation",
  "exercise",
  "scientific_coding",
]

const CHAT_LLM_MODEL_STORAGE_KEY = "advanced-rag.chat.llm-model"
const CHAT_EMBEDDING_MODEL_STORAGE_KEY = "advanced-rag.chat.embedding-model"

function readStoredModelSelection(key: string) {
  if (typeof window === "undefined") {
    return ""
  }
  return window.localStorage.getItem(key) || ""
}

function writeStoredModelSelection(key: string, value: string) {
  if (typeof window === "undefined") {
    return
  }

  const nextValue = value.trim()
  if (nextValue) {
    window.localStorage.setItem(key, nextValue)
  } else {
    window.localStorage.removeItem(key)
  }
}

function buildGenerationConfig(llmModel?: string, embeddingModel?: string) {
  const config: Record<string, string> = {}
  const nextLlmModel = llmModel?.trim()
  const nextEmbeddingModel = embeddingModel?.trim()

  if (nextLlmModel) {
    config.llm_model = nextLlmModel
  }
  if (nextEmbeddingModel) {
    config.embedding_model = nextEmbeddingModel
  }

  return config
}

function deepResearchAgentLabel(agentType?: string) {
  if (!agentType) {
    return "未知 Agent"
  }
  return deepResearchAgentLabels[agentType] || agentType
}

function deepResearchStatusTone(status?: string): "slate" | "sky" | "amber" | "rose" | "emerald" {
  if (status === "completed") {
    return "emerald"
  }
  if (status === "running") {
    return "sky"
  }
  if (status === "error") {
    return "rose"
  }
  if (status === "skipped") {
    return "amber"
  }
  return "slate"
}

function buildDeepResearchMarkdown(results: DeepResearchAgentResult[], htmlContent?: string) {
  const parts = results
    .filter((result) => result.content?.trim())
    .map((result) => {
      const title = result.title || deepResearchAgentLabel(result.agent_type)
      return `## ${title}\n\n${result.content.trim()}`
    })

  if (!parts.length && htmlContent?.trim()) {
    return "深度研究已完成，HTML 报告已生成，可在当前会话的深度研究面板中查看。"
  }

  return parts.join("\n\n---\n\n")
}

function formatPercent(value?: number | null) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : null
}

function formatScore(value?: number | null) {
  return typeof value === "number" ? value.toFixed(3) : null
}

function formatEvidenceLocation(item: EvidenceItem | CitationEvidenceRef | CitationEvidenceAudit) {
  const pageStart = "metadata" in item ? item.metadata?.page_start ?? item.page ?? null : item.page_start ?? item.page ?? null
  const pageEnd = "metadata" in item ? item.metadata?.page_end ?? item.page ?? null : item.page_end ?? item.page ?? null
  const pages =
    pageStart && pageEnd && pageStart !== pageEnd
      ? `第 ${pageStart}-${pageEnd} 页`
      : pageStart
        ? `第 ${pageStart} 页`
        : ""
  const section = "section_path" in item && item.section_path?.length ? item.section_path.join(" / ") : ""
  const chunk = typeof item.chunk_index === "number" ? `chunk ${item.chunk_index}` : ""
  return [pages, section, chunk].filter(Boolean).join(" · ")
}

function getEvidenceType(item: EvidenceItem) {
  return item.metadata?.content_type || "text"
}

function formatRiskLabels(reasons?: string[]) {
  return (reasons || []).map((reason) => citationRiskReasonLabel[reason] || reason)
}

function formatCitationQuality(quality?: CitationQuality | null) {
  if (!quality || typeof quality.evidence_count !== "number" || quality.evidence_count <= 0) {
    return ""
  }

  const bits: string[] = []
  if (quality.risk_level === "high") {
    bits.push("引用风险高")
  } else if (quality.risk_level === "medium") {
    bits.push("引用需复核")
  } else if (quality.status) {
    bits.push(`状态 ${quality.status}`)
  }

  const coverage = formatPercent(quality.coverage)
  if (coverage) {
    bits.push(`覆盖 ${coverage}`)
  }
  if (quality.valid_citation_ids?.length) {
    bits.push(`有效引用 ${quality.valid_citation_ids.join(", ")}`)
  }
  if (quality.invalid_citation_ids?.length) {
    bits.push(`无效 ${quality.invalid_citation_ids.join(", ")}`)
  }
  if (quality.duplicate_citation_ids?.length) {
    bits.push(`重复 ${quality.duplicate_citation_ids.join(", ")}`)
  }
  if (quality.unreferenced_top_evidence_ids?.length) {
    bits.push(`未引用高分 ${quality.unreferenced_top_evidence_ids.join(", ")}`)
  }
  return bits.join(" · ")
}

function formatEvidenceQuality(quality?: EvidenceQuality | null) {
  if (!quality || typeof quality.evidence_count !== "number" || quality.evidence_count <= 0) {
    return ""
  }

  const bits: string[] = []
  const artifactCoverage = formatPercent(quality.structured_artifact_coverage ?? quality.artifact_coverage)
  const locatorCoverage = formatPercent(quality.source_locator_coverage)
  if (artifactCoverage) {
    bits.push(`结构化 ${artifactCoverage}`)
  }
  if (locatorCoverage) {
    bits.push(`定位 ${locatorCoverage}`)
  }
  if ((quality.structured_missing_source_locator_count || quality.missing_source_locator_count || 0) > 0) {
    bits.push(`缺定位 ${quality.structured_missing_source_locator_count || quality.missing_source_locator_count}`)
  }
  if (quality.table_missing_structure_count > 0) {
    bits.push(`表格结构缺失 ${quality.table_missing_structure_count}`)
  }
  if (quality.ocr_low_confidence_source_count > 0) {
    bits.push(`低置信OCR ${quality.ocr_low_confidence_source_count}`)
  }
  if (!bits.length && quality.status === "pass") {
    bits.push("证据结构完整")
  }
  return bits.join(" · ")
}

function evidenceTitle(item: EvidenceItem | CitationEvidenceRef) {
  return item.document_title || item.document_id || item.chunk_id || item.id
}

function buildEvidenceDocumentUrl(item: EvidenceItem | CitationEvidenceRef | CitationEvidenceAudit) {
  if (!item.document_id) {
    return ""
  }

  const params = new URLSearchParams({ document_id: item.document_id })
  if (item.chunk_id) {
    params.set("chunk_id", item.chunk_id)
  }
  if (typeof item.chunk_index === "number") {
    params.set("chunk_index", String(item.chunk_index))
  }

  let contentType: string | undefined
  if ("content_type" in item) {
    contentType = item.content_type
  } else if ("metadata" in item) {
    contentType = item.metadata?.content_type
  }
  if (contentType) {
    params.set("content_type", contentType)
  }

  params.set("evidence_id", item.id)
  params.set("context_window", "6")
  return `/documents?${params.toString()}`
}

function DiagnosticBadge({ children, tone = "slate" }: { children: React.ReactNode; tone?: "slate" | "sky" | "amber" | "rose" | "emerald" }) {
  const classes = {
    slate: "bg-slate-100 text-slate-700",
    sky: "bg-sky-100 text-sky-800",
    amber: "bg-amber-100 text-amber-800",
    rose: "bg-rose-100 text-rose-800",
    emerald: "bg-emerald-100 text-emerald-800",
  }[tone]

  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${classes}`}>{children}</span>
}

function EvidenceRefList({
  title,
  items,
  tone,
}: {
  title: string
  items?: CitationEvidenceRef[]
  tone: "amber" | "rose"
}) {
  if (!items?.length) {
    return null
  }

  const panelClass =
    tone === "rose" ? "border-rose-200 bg-rose-50 text-rose-900" : "border-amber-200 bg-amber-50 text-amber-900"

  return (
    <div className={`rounded-lg border px-3 py-2 text-xs ${panelClass}`}>
      <div className="mb-1 font-medium">{title}</div>
      <div className="space-y-1">
        {items.slice(0, 4).map((item) => {
          const typeLabel = item.content_type ? evidenceTypeLabel[item.content_type] || item.content_type : null
          const location = formatEvidenceLocation(item)
          const documentUrl = buildEvidenceDocumentUrl(item)
          const sourceLocatorSummary = formatSourceLocatorSummary(item.source_locator)
          return (
            <div
              className="rounded-md border border-white/70 bg-white/70 px-2 py-1"
              key={`${title}-${item.id}-${item.chunk_id || item.chunk_index || item.score}`}
            >
              <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                <DiagnosticBadge tone={tone}>{item.id}</DiagnosticBadge>
                {typeLabel ? <DiagnosticBadge tone="sky">{typeLabel}</DiagnosticBadge> : null}
                {formatRiskLabels(item.risk_reasons).map((label) => (
                  <DiagnosticBadge key={`${item.id}-${label}`} tone="amber">
                    {label}
                  </DiagnosticBadge>
                ))}
                <span className="min-w-0 flex-1 truncate font-medium">{evidenceTitle(item)}</span>
                {formatScore(item.score) ? <span className="shrink-0 opacity-70">{formatScore(item.score)}</span> : null}
              </div>
              <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] opacity-75">
                {location ? <span>{location}</span> : null}
                {item.retrieval_type ? <span>{item.retrieval_type}</span> : null}
                {item.source_locator?.anchor_count ? <span>{item.source_locator.anchor_count} anchors</span> : null}
              </div>
              {item.preview ? <div className="mt-0.5 line-clamp-2 text-[11px] opacity-80">{item.preview}</div> : null}
              {sourceLocatorSummary ? (
                <div className="mt-1 rounded border border-emerald-100 bg-emerald-50 px-2 py-1 text-[11px] text-emerald-900">
                  来源定位：{sourceLocatorSummary}
                </div>
              ) : null}
              <SourceLocatorAnchorPreview compact locator={item.source_locator} />
              {item.quality_notes?.length ? (
                <div className="mt-0.5 text-[11px] opacity-75">{item.quality_notes.slice(0, 2).join(" · ")}</div>
              ) : null}
              {documentUrl ? (
                <a
                  className="mt-1 inline-flex text-[11px] font-medium text-sky-700 hover:text-sky-900 hover:underline"
                  href={documentUrl}
                >
                  定位到文档 chunk
                </a>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function MessageDiagnostics({ message }: { message: ConversationMessage }) {
  if (message.role === "user") {
    return null
  }

  const citationSummary = formatCitationQuality(message.citation_quality)
  const evidenceSummary = formatEvidenceQuality(message.evidence_quality)
  const hasDiagnostics = Boolean(
    message.evidence?.length ||
      message.evidence_quality ||
      message.citation_quality ||
      message.citation_warnings?.length,
  )

  if (!hasDiagnostics) {
    return null
  }

  return (
    <div className="mt-3 space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {message.sources?.length ? <DiagnosticBadge tone="sky">{message.sources.length} sources</DiagnosticBadge> : null}
        {message.evidence?.length ? (
          <DiagnosticBadge tone="emerald">{message.evidence.length} evidence</DiagnosticBadge>
        ) : null}
        {message.citation_quality?.risk_level ? (
          <DiagnosticBadge tone={message.citation_quality.risk_level === "high" ? "rose" : "amber"}>
            citation {message.citation_quality.risk_level}
          </DiagnosticBadge>
        ) : null}
        {typeof message.citation_quality?.coverage === "number" ? (
          <DiagnosticBadge tone="slate">coverage {formatPercent(message.citation_quality.coverage)}</DiagnosticBadge>
        ) : null}
      </div>

      {message.citation_warnings?.length ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {message.citation_warnings.join("；")}
        </div>
      ) : null}

      {citationSummary ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
          {citationSummary}
        </div>
      ) : null}

      {message.citation_quality?.recommendations?.length ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {message.citation_quality.recommendations.slice(0, 3).join("；")}
        </div>
      ) : null}

      {message.citation_quality?.evidence_citation_audit?.length ? (
        <details className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-800" open>
          <summary className="cursor-pointer font-medium">
            证据引用审计 · {message.citation_quality.evidence_citation_audit.length} 条
          </summary>
          <div className="mt-2 grid gap-1.5 md:grid-cols-2">
            {message.citation_quality.evidence_citation_audit.slice(0, 6).map((item) => {
              const typeLabel = item.content_type ? evidenceTypeLabel[item.content_type] || item.content_type : null
              const location = formatEvidenceLocation(item)
              const riskLabels = formatRiskLabels(item.risk_reasons)
              const documentUrl = buildEvidenceDocumentUrl(item)
              return (
                <div
                  className="rounded-md border border-slate-200 bg-slate-50/70 px-2 py-1"
                  key={`${item.id}-${item.chunk_id || item.chunk_index || item.document_id || item.score}-audit`}
                >
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                    <DiagnosticBadge>{item.id}</DiagnosticBadge>
                    {typeLabel ? <DiagnosticBadge tone="sky">{typeLabel}</DiagnosticBadge> : null}
                    {item.has_source_locator ? (
                      <DiagnosticBadge tone="emerald">有定位</DiagnosticBadge>
                    ) : (
                      <DiagnosticBadge tone="amber">缺定位</DiagnosticBadge>
                    )}
                    {riskLabels.map((label) => (
                      <DiagnosticBadge key={`${item.id}-${label}`} tone="amber">
                        {label}
                      </DiagnosticBadge>
                    ))}
                    {formatScore(item.score) ? <span className="ml-auto text-[11px] opacity-70">{formatScore(item.score)}</span> : null}
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-slate-500">
                    {location ? <span>{location}</span> : null}
                    {item.retrieval_type ? <span>{item.retrieval_type}</span> : null}
                    {typeof item.source_anchor_count === "number" ? <span>{item.source_anchor_count} anchors</span> : null}
                    {item.has_table_source ? <span>表格来源</span> : null}
                    {item.has_image_source ? <span>图片来源</span> : null}
                    {item.has_bbox ? <span>bbox</span> : null}
                    {item.artifact_quality_status ? <span>artifact {item.artifact_quality_status}</span> : null}
                  </div>
                  {item.quality_notes?.length ? (
                    <div className="mt-0.5 text-[11px] text-amber-700">{item.quality_notes.slice(0, 2).join(" · ")}</div>
                  ) : null}
                  {documentUrl ? (
                    <a
                      className="mt-1 inline-flex text-[11px] font-medium text-sky-700 hover:text-sky-900 hover:underline"
                      href={documentUrl}
                    >
                      定位到文档 chunk
                    </a>
                  ) : null}
                </div>
              )
            })}
          </div>
        </details>
      ) : null}

      <EvidenceRefList title="已引用需复核证据" items={message.citation_quality?.cited_risky_evidence} tone="rose" />
      <EvidenceRefList title="未引用高分证据" items={message.citation_quality?.unreferenced_top_evidence} tone="amber" />

      {message.evidence?.length ? (
        <details className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
          <summary className="cursor-pointer font-medium">检索证据 · {message.evidence.length} 条</summary>
          <div className="mt-2 space-y-1">
            {message.evidence.slice(0, 5).map((item) => {
              const type = getEvidenceType(item)
              const location = formatEvidenceLocation(item)
              const documentUrl = buildEvidenceDocumentUrl(item)
              const sourceLocatorSummary = formatSourceLocatorSummary(item.metadata?.source_locator)
              return (
                <div className="rounded-md border border-emerald-100 bg-white/80 px-2 py-1" key={`${item.id}-${item.chunk_id}`}>
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                    <DiagnosticBadge tone="emerald">{item.id}</DiagnosticBadge>
                    <DiagnosticBadge tone="sky">{evidenceTypeLabel[type] || type}</DiagnosticBadge>
                    <span className="min-w-0 flex-1 truncate font-medium">{evidenceTitle(item)}</span>
                    {formatScore(item.score) ? <span className="shrink-0 opacity-70">{formatScore(item.score)}</span> : null}
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] opacity-75">
                    {location ? <span>{location}</span> : null}
                    {item.retrieval_type ? <span>{item.retrieval_type}</span> : null}
                    {item.metadata?.source_locator?.anchor_count ? (
                      <span>{item.metadata.source_locator.anchor_count} anchors</span>
                    ) : null}
                  </div>
                  <div className="mt-0.5 line-clamp-2 text-[11px] opacity-80">{item.metadata?.preview || item.text}</div>
                  {sourceLocatorSummary ? (
                    <div className="mt-1 rounded border border-emerald-100 bg-emerald-50 px-2 py-1 text-[11px] text-emerald-900">
                      来源定位：{sourceLocatorSummary}
                    </div>
                  ) : null}
                  <SourceLocatorAnchorPreview compact locator={item.metadata?.source_locator} />
                  <ArtifactSourceLocatorPreview artifact={item.metadata?.artifact} />
                  {documentUrl ? (
                    <a
                      className="mt-1 inline-flex text-[11px] font-medium text-sky-700 hover:text-sky-900 hover:underline"
                      href={documentUrl}
                    >
                      定位到文档 chunk
                    </a>
                  ) : null}
                </div>
              )
            })}
          </div>
        </details>
      ) : null}

      {evidenceSummary ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
          {evidenceSummary}
        </div>
      ) : null}
    </div>
  )
}

function DeepResearchPanel({
  gate,
  statuses,
  results,
  htmlContent,
}: {
  gate?: DeepResearchEvaluation | null
  statuses: DeepResearchAgentStatus[]
  results: DeepResearchAgentResult[]
  htmlContent: string
}) {
  if (!gate && !statuses.length && !results.length && !htmlContent) {
    return null
  }

  return (
    <div className="rounded-2xl border border-sky-200 bg-sky-50/80 p-4 text-sm text-slate-800">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-semibold text-sky-950">
          <BrainCircuit className="size-4" />
          深度研究工作流
        </div>
        {gate ? (
          <Badge className="bg-white text-slate-700">
            评分 {gate.score}/{gate.threshold}
          </Badge>
        ) : null}
      </div>

      {gate?.reasons?.length ? (
        <div className="mb-3 rounded-xl border border-sky-100 bg-white px-3 py-2 text-xs leading-5 text-slate-600">
          {gate.reasons.slice(0, 3).join("；")}
        </div>
      ) : null}

      {statuses.length ? (
        <div className="mb-3 grid gap-2 md:grid-cols-2">
          {statuses.map((status) => (
            <div className="rounded-xl border border-sky-100 bg-white px-3 py-2" key={status.agent_type}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-slate-950">{deepResearchAgentLabel(status.agent_type)}</span>
                <DiagnosticBadge tone={deepResearchStatusTone(status.status)}>{status.status}</DiagnosticBadge>
              </div>
              {typeof status.progress === "number" ? (
                <div className="mt-2 h-1.5 rounded-full bg-sky-100">
                  <div className="h-1.5 rounded-full bg-sky-600" style={{ width: `${Math.max(0, Math.min(100, status.progress))}%` }} />
                </div>
              ) : null}
              {status.current_step || status.details ? (
                <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{status.current_step || status.details}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {results.length ? (
        <details className="mb-3 rounded-xl border border-sky-100 bg-white px-3 py-2" open>
          <summary className="cursor-pointer text-sm font-medium text-slate-950">Agent 结果 · {results.length} 条</summary>
          <div className="mt-2 space-y-2">
            {results.map((result) => (
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2" key={result.agent_type}>
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <DiagnosticBadge tone="sky">{deepResearchAgentLabel(result.agent_type)}</DiagnosticBadge>
                  {typeof result.confidence === "number" ? (
                    <DiagnosticBadge tone="slate">confidence {result.confidence.toFixed(2)}</DiagnosticBadge>
                  ) : null}
                  {result.evidence_ids?.length ? (
                    <DiagnosticBadge tone="emerald">evidence {result.evidence_ids.length}</DiagnosticBadge>
                  ) : null}
                </div>
                <div className="line-clamp-4 whitespace-pre-wrap text-xs leading-5 text-slate-600">{result.content}</div>
              </div>
            ))}
          </div>
        </details>
      ) : null}

      {htmlContent ? (
        <details className="rounded-xl border border-sky-100 bg-white px-3 py-2" open>
          <summary className="cursor-pointer text-sm font-medium text-slate-950">HTML 报告</summary>
          <iframe
            className="mt-3 h-[420px] w-full rounded-lg border border-slate-200 bg-white"
            sandbox=""
            srcDoc={htmlContent}
            title="深度研究报告"
          />
        </details>
      ) : null}
    </div>
  )
}

export function ChatPlayground() {
  const queryClient = useQueryClient()
  const { activeConversationId, setActiveConversationId, selectedKnowledgeSpaceId, enableRag, setEnableRag } =
    useUiStore()
  const [prompt, setPrompt] = useState("")
  const [draftAnswer, setDraftAnswer] = useState("")
  const [editingConversationId, setEditingConversationId] = useState<string | null>(null)
  const [conversationTitleDraft, setConversationTitleDraft] = useState("")
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
  const [messageDraft, setMessageDraft] = useState("")
  const [actionMessage, setActionMessage] = useState<{ tone: "error" | "success"; text: string } | null>(null)
  const [attachments, setAttachments] = useState<ChatAttachment[]>([])
  const [deepResearchEnabled, setDeepResearchEnabled] = useState(() => {
    if (typeof window === "undefined") {
      return false
    }
    return window.localStorage.getItem("deepResearchEnabled") === "true"
  })
  const [selectedLlmModel, setSelectedLlmModel] = useState(() => readStoredModelSelection(CHAT_LLM_MODEL_STORAGE_KEY))
  const [selectedEmbeddingModel, setSelectedEmbeddingModel] = useState(() =>
    readStoredModelSelection(CHAT_EMBEDDING_MODEL_STORAGE_KEY),
  )
  const [deepResearchGate, setDeepResearchGate] = useState<DeepResearchEvaluation | null>(null)
  const [deepResearchStatuses, setDeepResearchStatuses] = useState<DeepResearchAgentStatus[]>([])
  const [deepResearchResults, setDeepResearchResults] = useState<DeepResearchAgentResult[]>([])
  const [deepResearchHtml, setDeepResearchHtml] = useState("")
  const [streamingMeta, setStreamingMeta] = useState<{ evidence: number; sources: number; status: string }>({
    evidence: 0,
    sources: 0,
    status: "Idle",
  })
  const messageListRef = useRef<HTMLDivElement>(null)
  const attachmentInputRef = useRef<HTMLInputElement>(null)
  const attachmentSubscriptionsRef = useRef<Record<string, () => void>>({})

  const conversationsQuery = useQuery({
    queryKey: ["conversations"],
    queryFn: async () => {
      const result = await api.getConversations()
      if (result.error) {
        throw new Error(result.error)
      }
      return result.data
    },
  })

  const conversationDetailQuery = useQuery({
    queryKey: ["conversation", activeConversationId],
    enabled: Boolean(activeConversationId),
    queryFn: async () => {
      const result = await api.getConversation(activeConversationId!)
      if (result.error) {
        throw new Error(result.error)
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

  const modelNames = useMemo(() => modelsQuery.data?.models?.map((model) => model.name).filter(Boolean) || [], [modelsQuery.data])
  const activeLlmModel = selectedLlmModel.trim() || modelNames[0] || ""
  const activeEmbeddingModel = selectedEmbeddingModel.trim()
  const generationConfig = useMemo(
    () => buildGenerationConfig(activeLlmModel, activeEmbeddingModel),
    [activeEmbeddingModel, activeLlmModel],
  )

  useEffect(() => {
    if (!activeConversationId && conversationsQuery.data?.conversations?.length) {
      setActiveConversationId(conversationsQuery.data.conversations[0].id)
    }
  }, [activeConversationId, conversationsQuery.data, setActiveConversationId])

  useEffect(() => {
    if (!messageListRef.current) {
      return
    }

    messageListRef.current.scrollTop = messageListRef.current.scrollHeight
  }, [conversationDetailQuery.data, draftAnswer])

  useEffect(() => {
    window.localStorage.setItem("deepResearchEnabled", String(deepResearchEnabled))
  }, [deepResearchEnabled])

  useEffect(() => {
    writeStoredModelSelection(CHAT_LLM_MODEL_STORAGE_KEY, selectedLlmModel)
  }, [selectedLlmModel])

  useEffect(() => {
    writeStoredModelSelection(CHAT_EMBEDDING_MODEL_STORAGE_KEY, selectedEmbeddingModel)
  }, [selectedEmbeddingModel])

  useEffect(() => {
    const processingAttachments = attachments.filter((attachment) => isAttachmentProcessing(attachment.status))
    const processingKeys = new Set<string>()

    for (const attachment of processingAttachments) {
      const key = `${attachment.conversation_id}:${attachment.file_id}`
      processingKeys.add(key)

      if (attachmentSubscriptionsRef.current[key]) {
        continue
      }

      attachmentSubscriptionsRef.current[key] = api.subscribeConversationAttachmentProgress(
        attachment.conversation_id,
        attachment.file_id,
        (status) => {
          setAttachments((current) =>
            current.map((item) =>
              item.file_id === attachment.file_id && item.conversation_id === attachment.conversation_id
                ? mergeAttachmentStatus(item, status)
                : item,
            ),
          )
        },
        (status) => {
          setAttachments((current) =>
            current.map((item) =>
              item.file_id === attachment.file_id && item.conversation_id === attachment.conversation_id
                ? mergeAttachmentStatus(item, status)
                : item,
            ),
          )
          attachmentSubscriptionsRef.current[key]?.()
          delete attachmentSubscriptionsRef.current[key]
        },
        (message) => {
          setAttachments((current) =>
            current.map((item) =>
              item.file_id === attachment.file_id && item.conversation_id === attachment.conversation_id
                ? { ...item, error: message }
                : item,
            ),
          )
          attachmentSubscriptionsRef.current[key]?.()
          delete attachmentSubscriptionsRef.current[key]
        },
      )
    }

    for (const [key, unsubscribe] of Object.entries(attachmentSubscriptionsRef.current)) {
      if (!processingKeys.has(key)) {
        unsubscribe()
        delete attachmentSubscriptionsRef.current[key]
      }
    }
  }, [attachments])

  useEffect(() => {
    return () => {
      for (const unsubscribe of Object.values(attachmentSubscriptionsRef.current)) {
        unsubscribe()
      }
      attachmentSubscriptionsRef.current = {}
    }
  }, [])

  const createConversationMutation = useMutation({
    mutationFn: async () => {
      const result = await api.createConversation("TanStack 新对话")
      if (result.error || !result.data) {
        throw new Error(result.error || "创建对话失败")
      }
      return result.data
    },
    onSuccess: async (data) => {
      setActiveConversationId(data.id)
      await queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  const uploadAttachmentMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!selectedKnowledgeSpaceId) {
        throw new Error("请先选择知识空间")
      }

      let conversationId = activeConversationId
      if (!conversationId) {
        const created = await createConversationMutation.mutateAsync()
        conversationId = created.id
      }

      const result = await api.uploadConversationAttachment(conversationId, selectedKnowledgeSpaceId, file)
      if (result.error || !result.data) {
        throw new Error(result.error || "附件上传失败")
      }

      return {
        file_id: result.data.file_id,
        conversation_id: conversationId,
        document_id: result.data.document_id,
        filename: file.name,
        status: result.data.status || "processing",
        progress_percentage: 5,
        current_stage: result.data.message || "已上传",
        message: result.data.message,
        task: result.data.task,
      } satisfies ChatAttachment
    },
    onSuccess: async (attachment) => {
      setAttachments((current) => [
        ...current.filter((item) => !(item.conversation_id === attachment.conversation_id && item.file_id === attachment.file_id)),
        attachment,
      ])
      setActionMessage({ tone: "success", text: "附件已上传，正在处理" })
      await queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
    onError: (error) => {
      setActionMessage({ tone: "error", text: error instanceof Error ? error.message : "附件上传失败" })
    },
  })

  const renameConversationMutation = useMutation({
    mutationFn: async ({ conversationId, title }: { conversationId: string; title: string }) => {
      const result = await api.updateConversation(conversationId, { title })
      if (result.error || !result.data) {
        throw new Error(result.error || "重命名会话失败")
      }
      return result.data
    },
    onSuccess: async (data) => {
      queryClient.setQueryData(["conversation", data.id], (existing: ConversationDetail | undefined) =>
        existing ? { ...existing, title: data.title, updated_at: data.updated_at ?? existing.updated_at } : existing,
      )
      setEditingConversationId(null)
      setConversationTitleDraft("")
      setActionMessage({ tone: "success", text: "会话已重命名" })
      await queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
    onError: (error) => {
      setActionMessage({ tone: "error", text: error instanceof Error ? error.message : "重命名会话失败" })
    },
  })

  const deleteConversationMutation = useMutation({
    mutationFn: async (conversationId: string) => {
      const result = await api.deleteConversation(conversationId)
      if (result.error) {
        throw new Error(result.error)
      }
      return conversationId
    },
    onSuccess: async (conversationId) => {
      queryClient.removeQueries({ queryKey: ["conversation", conversationId] })
      if (activeConversationId === conversationId) {
        const nextConversation = conversationsQuery.data?.conversations.find((item) => item.id !== conversationId)
        setActiveConversationId(nextConversation?.id)
      }
      setActionMessage({ tone: "success", text: "会话已删除" })
      await queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
    onError: (error) => {
      setActionMessage({ tone: "error", text: error instanceof Error ? error.message : "删除会话失败" })
    },
  })

  const updateMessageMutation = useMutation({
    mutationFn: async ({ messageId, content }: { messageId: string; content: string }) => {
      if (!activeConversationId) {
        throw new Error("未选择会话")
      }
      const result = await api.updateConversationMessage(activeConversationId, messageId, { content })
      if (result.error || !result.data) {
        throw new Error(result.error || "更新消息失败")
      }
      return { messageId, content, timestamp: result.data.timestamp }
    },
    onSuccess: async ({ messageId, content, timestamp }) => {
      if (activeConversationId) {
        queryClient.setQueryData(["conversation", activeConversationId], (existing: ConversationDetail | undefined) =>
          existing
            ? {
                ...existing,
                messages: existing.messages.map((message) =>
                  message.message_id === messageId ? { ...message, content, timestamp: timestamp || message.timestamp } : message,
                ),
              }
            : existing,
        )
        await queryClient.invalidateQueries({ queryKey: ["conversation", activeConversationId] })
      }
      setEditingMessageId(null)
      setMessageDraft("")
      setActionMessage({ tone: "success", text: "消息已更新" })
    },
    onError: (error) => {
      setActionMessage({ tone: "error", text: error instanceof Error ? error.message : "更新消息失败" })
    },
  })

  const resetDeepResearchRun = () => {
    setDeepResearchGate(null)
    setDeepResearchStatuses([])
    setDeepResearchResults([])
    setDeepResearchHtml("")
  }

  const upsertDeepResearchStatus = (next: DeepResearchAgentStatus) => {
    setDeepResearchStatuses((current) => {
      const exists = current.some((status) => status.agent_type === next.agent_type)
      if (exists) {
        return current.map((status) => (status.agent_type === next.agent_type ? { ...status, ...next } : status))
      }
      return [...current, next]
    })
  }

  const updateDeepResearchResult = (result: DeepResearchAgentResult) => {
    setDeepResearchResults((current) => {
      const exists = current.some((item) => item.agent_type === result.agent_type)
      if (exists) {
        return current.map((item) => (item.agent_type === result.agent_type ? { ...item, ...result } : item))
      }
      return [...current, result]
    })
  }

  const regenerateMessageMutation = useMutation({
    mutationFn: async (message: ConversationMessage) => {
      if (!activeConversationId) {
        throw new Error("未选择会话")
      }
      if (!message.message_id || message.role !== "user") {
        throw new Error("只能重新生成用户消息对应的回答")
      }

      const conversationId = activeConversationId
      const currentConversation =
        queryClient.getQueryData<ConversationDetail>(["conversation", conversationId]) || conversationDetailQuery.data

      if (!currentConversation) {
        throw new Error("当前会话尚未加载")
      }

      const messageIndex = currentConversation.messages.findIndex((item) => item.message_id === message.message_id)
      if (messageIndex < 0) {
        throw new Error("找不到要重新生成的消息")
      }

      const regenerateResult = await api.regenerateConversationMessage(conversationId, message.message_id)
      if (regenerateResult.error) {
        throw new Error(regenerateResult.error)
      }

      const keptMessages = currentConversation.messages.slice(0, messageIndex + 1)
      queryClient.setQueryData(["conversation", conversationId], {
        ...currentConversation,
        messages: keptMessages,
      })

      setDraftAnswer("")
      setStreamingMeta({ evidence: 0, sources: 0, status: "Regenerating" })
      let assistantText = ""
      let finalEvent: ChatStreamEvent | undefined
      let streamError: string | undefined

      await api.streamChat(
        {
          query: message.content,
          conversation_id: conversationId,
          knowledge_space_ids: selectedKnowledgeSpaceId ? [selectedKnowledgeSpaceId] : undefined,
          enable_rag: enableRag,
          generation_config: generationConfig,
        },
        (event) => {
          finalEvent = event.done ? event : finalEvent

          if (event.error) {
            streamError = event.error
            setDraftAnswer(`请求失败：${event.error}`)
            setStreamingMeta({ evidence: 0, sources: 0, status: "Error" })
            return
          }

          if (event.content) {
            assistantText += event.content
            setDraftAnswer(assistantText)
          }

          if (event.done) {
            queryClient.setQueryData(["conversation", conversationId], (existing: ConversationDetail | undefined) => ({
              ...(existing || currentConversation),
              messages: [
                ...(existing?.messages || keptMessages),
                {
                  role: "assistant",
                  content: assistantText,
                  timestamp: new Date().toISOString(),
                  sources: event.sources,
                  evidence: event.evidence,
                  evidence_quality: event.evidence_quality,
                  citation_warnings: event.citation_warnings,
                  citation_quality: event.citation_quality,
                  recommended_resources: event.recommended_resources,
                },
              ],
            }))
            setStreamingMeta({
              evidence: event.evidence?.length || 0,
              sources: event.sources?.length || 0,
              status: "Done",
            })
            setDraftAnswer("")
          }
        },
      )

      if (streamError) {
        throw new Error(streamError)
      }

      if (assistantText.trim()) {
        await api.addConversationMessage(conversationId, {
          role: "assistant",
          content: assistantText,
          sources: finalEvent?.sources,
          evidence: finalEvent?.evidence,
          evidence_quality: finalEvent?.evidence_quality,
          citation_warnings: finalEvent?.citation_warnings,
          citation_quality: finalEvent?.citation_quality,
          recommended_resources: finalEvent?.recommended_resources,
        })
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["conversations"] }),
        queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] }),
      ])
    },
    onSuccess: () => {
      setActionMessage({ tone: "success", text: "回答已重新生成" })
    },
    onError: (error) => {
      setActionMessage({ tone: "error", text: error instanceof Error ? error.message : "重新生成失败" })
    },
  })

  const sendMutation = useMutation({
    mutationFn: async (question: string) => {
      let conversationId = activeConversationId

      if (!conversationId) {
        const created = await createConversationMutation.mutateAsync()
        conversationId = created.id
      }

      const processingAttachments = attachments.filter(
        (attachment) => attachment.conversation_id === conversationId && isAttachmentProcessing(attachment.status),
      )
      if (processingAttachments.length > 0) {
        throw new Error("请等待附件处理完成后再发送消息")
      }

      const currentConversation =
        queryClient.getQueryData<ConversationDetail>(["conversation", conversationId]) ||
        conversationDetailQuery.data ||
        ({
          id: conversationId,
          title: "TanStack 新对话",
          messages: [],
        } satisfies ConversationDetail)

      queryClient.setQueryData(["conversation", conversationId], {
        ...currentConversation,
        messages: [
          ...(currentConversation.messages || []),
          {
            role: "user",
            content: question,
            timestamp: new Date().toISOString(),
          },
        ],
      })

      await api.addConversationMessage(conversationId, {
        role: "user",
        content: question,
      })

      resetDeepResearchRun()
      setDraftAnswer("")
      let shouldUseDeepResearch = deepResearchEnabled

      if (shouldUseDeepResearch) {
        setStreamingMeta({ evidence: 0, sources: 0, status: "Evaluating" })
        const gate = await api.evaluateDeepResearch({ query: question, conversation_id: conversationId })
        if (gate.error || !gate.data) {
          shouldUseDeepResearch = false
          setActionMessage({ tone: "error", text: `深度研究预评估失败，已改走常规模式：${gate.error || "未知错误"}` })
        } else {
          setDeepResearchGate(gate.data)
          const reasons = gate.data.reasons.slice(0, 2).join("；")
          if (!gate.data.should_deep_research) {
            shouldUseDeepResearch = false
            setActionMessage({
              tone: "success",
              text: `本次问题评分 ${gate.data.score}/${gate.data.threshold}，先走常规模式：${reasons}`,
            })
          } else {
            setActionMessage({
              tone: "success",
              text: `已进入深度研究，评分 ${gate.data.score}/${gate.data.threshold}：${reasons}`,
            })
          }
        }
      }

      if (shouldUseDeepResearch) {
        setStreamingMeta({ evidence: 0, sources: 0, status: "Deep research" })
        setDraftAnswer("深度研究已启动，正在规划多 Agent 任务...")
        setDeepResearchStatuses(
          DEFAULT_DEEP_RESEARCH_AGENTS.map((agentType, index) => ({
            agent_type: agentType,
            status: index === 0 ? "running" : "pending",
            current_step: index === 0 ? "分析问题并规划研究任务" : undefined,
            progress: index === 0 ? 0 : undefined,
          })),
        )

        const resultsMap = new Map<string, DeepResearchAgentResult>()
        let htmlReport = ""
        let streamError: string | undefined

        await api.streamDeepResearch(
          {
            query: question,
            conversation_id: conversationId,
            knowledge_space_ids: selectedKnowledgeSpaceId ? [selectedKnowledgeSpaceId] : undefined,
            generation_config: generationConfig,
          },
          (event: DeepResearchStreamEvent) => {
            if (event.error) {
              streamError = event.error
              setDraftAnswer(`深度研究失败：${event.error}`)
              setStreamingMeta({ evidence: 0, sources: 0, status: "Error" })
              return
            }

            if (event.type === "planning") {
              const selectedAgents = event.selected_agents?.length ? event.selected_agents : DEFAULT_DEEP_RESEARCH_AGENTS.slice(1)
              setDeepResearchStatuses(
                DEFAULT_DEEP_RESEARCH_AGENTS.map((agentType) => {
                  if (agentType === "coordinator") {
                    return {
                      agent_type: agentType,
                      status: "completed",
                      details: event.reasoning || event.content || "任务规划完成",
                      progress: 100,
                    }
                  }
                  return {
                    agent_type: agentType,
                    status: selectedAgents.includes(agentType) ? "pending" : "skipped",
                    details: selectedAgents.includes(agentType) ? undefined : "协调规划未选择此 Agent",
                  }
                }),
              )
              setDraftAnswer(`## 研究规划\n\n${event.content || event.reasoning || "任务规划完成"}`)
              return
            }

            if (event.type === "agent_status" && event.agent_type) {
              upsertDeepResearchStatus({
                agent_type: event.agent_type,
                status: event.status || "running",
                current_step: event.current_step,
                progress: event.progress,
                details: event.details,
                dependencies: Array.isArray(event.dependencies) ? event.dependencies.map(String) : undefined,
                started_at: event.started_at,
                completed_at: event.completed_at,
              })
              return
            }

            if ((event.type === "agent_result" || event.type === "markdown" || event.type === "text") && event.content) {
              const agentType = event.agent_type || "summary"
              const result: DeepResearchAgentResult = {
                agent_type: agentType,
                content: event.content,
                title: event.title,
                sources: event.sources,
                evidence: event.evidence,
                evidence_ids: event.evidence_ids,
                claims: event.claims,
                open_questions: event.open_questions,
                confidence: event.confidence,
              }
              resultsMap.set(agentType, result)
              updateDeepResearchResult(result)
              upsertDeepResearchStatus({
                agent_type: agentType,
                status: "completed",
                progress: 100,
                details: event.title || "工作完成",
              })
              setDraftAnswer(buildDeepResearchMarkdown(Array.from(resultsMap.values())))
              return
            }

            if (event.type === "html" && event.content) {
              htmlReport = event.content
              setDeepResearchHtml(event.content)
              setStreamingMeta({ evidence: 0, sources: 0, status: "Report ready" })
              return
            }

            if (event.done) {
              setDeepResearchStatuses((current) =>
                current.map((status) =>
                  status.status === "running" ? { ...status, status: "completed", progress: status.progress ?? 100 } : status,
                ),
              )
              setStreamingMeta({ evidence: 0, sources: 0, status: "Done" })
            }
          },
        )

        if (streamError) {
          throw new Error(streamError)
        }

        const finalResults = Array.from(resultsMap.values())
        const finalContent = buildDeepResearchMarkdown(finalResults, htmlReport)
        if (finalContent.trim()) {
          queryClient.setQueryData(["conversation", conversationId], (existing: ConversationDetail | undefined) => ({
            ...(existing || currentConversation),
            messages: [
              ...(existing?.messages || currentConversation.messages || []),
              {
                role: "assistant",
                content: finalContent,
                timestamp: new Date().toISOString(),
              },
            ],
          }))
          await api.addConversationMessage(conversationId, {
            role: "assistant",
            content: finalContent,
          })
        }

        setDraftAnswer("")
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["conversations"] }),
          queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] }),
        ])
        return
      }

      setStreamingMeta({ evidence: 0, sources: 0, status: "Streaming" })
      let assistantText = ""
      let finalEvent: ChatStreamEvent | undefined
      let streamError: string | undefined

      await api.streamChat(
        {
          query: question,
          conversation_id: conversationId,
          knowledge_space_ids: selectedKnowledgeSpaceId ? [selectedKnowledgeSpaceId] : undefined,
          enable_rag: enableRag,
          generation_config: generationConfig,
        },
        (event) => {
          finalEvent = event.done ? event : finalEvent

          if (event.error) {
            streamError = event.error
            setDraftAnswer(`请求失败：${event.error}`)
            setStreamingMeta({ evidence: 0, sources: 0, status: "Error" })
            return
          }

          if (event.content) {
            assistantText += event.content
            setDraftAnswer(assistantText)
          }

          if (event.done) {
            queryClient.setQueryData(["conversation", conversationId], (existing: ConversationDetail | undefined) => ({
              ...(existing || currentConversation),
              messages: [
                ...(existing?.messages || currentConversation.messages || []),
                {
                  role: "assistant",
                  content: assistantText,
                  timestamp: new Date().toISOString(),
                  sources: event.sources,
                  evidence: event.evidence,
                  evidence_quality: event.evidence_quality,
                  citation_warnings: event.citation_warnings,
                  citation_quality: event.citation_quality,
                  recommended_resources: event.recommended_resources,
                },
              ],
            }))
            setStreamingMeta({
              evidence: event.evidence?.length || 0,
              sources: event.sources?.length || 0,
              status: "Done",
            })
            setDraftAnswer("")
          }
        },
      )

      if (streamError) {
        throw new Error(streamError)
      }

      if (assistantText.trim()) {
        await api.addConversationMessage(conversationId, {
          role: "assistant",
          content: assistantText,
          sources: finalEvent?.sources,
          evidence: finalEvent?.evidence,
          evidence_quality: finalEvent?.evidence_quality,
          citation_warnings: finalEvent?.citation_warnings,
          citation_quality: finalEvent?.citation_quality,
          recommended_resources: finalEvent?.recommended_resources,
        })
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["conversations"] }),
        queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] }),
      ])
    },
  })

  const messages = conversationDetailQuery.data?.messages || []
  const errors = [
    conversationsQuery.error instanceof Error ? `会话列表加载失败：${conversationsQuery.error.message}` : null,
    conversationDetailQuery.error instanceof Error ? `会话详情加载失败：${conversationDetailQuery.error.message}` : null,
    modelsQuery.error instanceof Error ? `模型列表加载失败：${modelsQuery.error.message}` : null,
    sendMutation.error instanceof Error ? `消息发送失败：${sendMutation.error.message}` : null,
  ].filter(Boolean) as string[]

  const allMessages: ConversationMessage[] =
    draftAnswer.trim().length > 0
      ? [
          ...messages,
          {
            role: "assistant" as const,
            content: draftAnswer,
            timestamp: new Date().toISOString(),
          },
        ]
      : messages
  const activeAttachments = activeConversationId
    ? attachments.filter((attachment) => attachment.conversation_id === activeConversationId)
    : []
  const hasProcessingAttachments = activeAttachments.some((attachment) => isAttachmentProcessing(attachment.status))

  return (
    <div className="grid gap-5 xl:grid-cols-[340px_minmax(0,1fr)]">
      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle>Conversation Stack</CardTitle>
          <CardDescription>TanStack Query 管理列表与详情缓存，Zustand 保存当前会话与 RAG 开关。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button
            className="w-full"
            onClick={() => createConversationMutation.mutate()}
            variant="secondary"
          >
            <Sparkles className="size-4" />
            新建会话
          </Button>

          <div className="space-y-2">
            {(conversationsQuery.data?.conversations || []).map((conversation) => (
              <div
                key={conversation.id}
                className={`rounded-2xl border p-3 transition-all ${
                  activeConversationId === conversation.id
                    ? "border-sky-950 bg-sky-950 text-white shadow-[0_12px_24px_rgba(12,74,110,0.16)]"
                    : "border-[var(--blue-line)] bg-white text-slate-700 hover:bg-[var(--surface-blue)] hover:text-sky-950"
                }`}
              >
                {editingConversationId === conversation.id ? (
                  <div className="space-y-2">
                    <Input
                      className="h-9 bg-white text-slate-950"
                      onChange={(event) => setConversationTitleDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          const title = conversationTitleDraft.trim()
                          if (title) {
                            renameConversationMutation.mutate({ conversationId: conversation.id, title })
                          }
                        }
                        if (event.key === "Escape") {
                          setEditingConversationId(null)
                        }
                      }}
                      value={conversationTitleDraft}
                    />
                    <div className="flex gap-2">
                      <Button
                        disabled={!conversationTitleDraft.trim() || renameConversationMutation.isPending}
                        onClick={() =>
                          renameConversationMutation.mutate({
                            conversationId: conversation.id,
                            title: conversationTitleDraft.trim(),
                          })
                        }
                        size="sm"
                      >
                        <Check className="size-3.5" />
                        保存
                      </Button>
                      <Button
                        onClick={() => {
                          setEditingConversationId(null)
                          setConversationTitleDraft("")
                        }}
                        size="sm"
                        variant="secondary"
                      >
                        <X className="size-3.5" />
                        取消
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="grid gap-2">
                    <button
                      className="min-w-0 text-left focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-sky-100"
                      onClick={() => setActiveConversationId(conversation.id)}
                      type="button"
                    >
                      <div className="truncate text-sm font-medium">{conversation.title}</div>
                      <div className="mt-1 text-xs opacity-70">{conversation.message_count} messages</div>
                    </button>
                    <div className="flex gap-1.5">
                      <Button
                        className={activeConversationId === conversation.id ? "bg-white/10 text-white hover:bg-white/20" : ""}
                        onClick={() => {
                          setEditingConversationId(conversation.id)
                          setConversationTitleDraft(conversation.title)
                        }}
                        size="icon-xs"
                        title="重命名"
                        variant={activeConversationId === conversation.id ? "ghost" : "secondary"}
                      >
                        <Pencil className="size-3" />
                      </Button>
                      <Button
                        className={activeConversationId === conversation.id ? "bg-white/10 text-white hover:bg-white/20" : ""}
                        disabled={deleteConversationMutation.isPending}
                        onClick={() => {
                          if (window.confirm(`删除会话“${conversation.title}”？`)) {
                            deleteConversationMutation.mutate(conversation.id)
                          }
                        }}
                        size="icon-xs"
                        title="删除"
                        variant={activeConversationId === conversation.id ? "ghost" : "secondary"}
                      >
                        <Trash2 className="size-3" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4">
        <Card>
          <CardHeader className="pb-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle>Streaming Chat</CardTitle>
                <CardDescription>直接对接 `/api/chat` SSE，作为 TanStack 版聊天主工作区。</CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge>{streamingMeta.status}</Badge>
                <Badge>sources {streamingMeta.sources}</Badge>
                <Badge>evidence {streamingMeta.evidence}</Badge>
                <Badge>{enableRag ? "RAG on" : "RAG off"}</Badge>
                <Badge>{deepResearchEnabled ? "Deep research on" : "Deep research off"}</Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {errors.length > 0 ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {errors.map((error) => (
                  <div key={error}>{error}</div>
                ))}
              </div>
            ) : null}
            {actionMessage ? (
              <div
                className={`rounded-2xl border px-4 py-3 text-sm ${
                  actionMessage.tone === "success"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-rose-200 bg-rose-50 text-rose-700"
                }`}
              >
                {actionMessage.text}
              </div>
            ) : null}
            <DeepResearchPanel
              gate={deepResearchGate}
              htmlContent={deepResearchHtml}
              results={deepResearchResults}
              statuses={deepResearchStatuses}
            />

            <div
              className="blue-panel h-[440px] space-y-4 overflow-y-auto rounded-2xl p-4"
              ref={messageListRef}
            >
              {allMessages.length === 0 ? (
                <div className="flex h-full items-center justify-center text-center text-slate-500">
                  发一条消息试试，右侧文档面板选择知识空间后可以直接走 RAG 检索。
                </div>
              ) : (
                allMessages.map((message, index) => (
                  <div
                    key={`${message.role}-${index}-${message.timestamp}`}
                    className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    {message.role === "assistant" && (
                      <div className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-sky-100 text-sky-900">
                        <Bot className="size-4" />
                      </div>
                    )}
                    <div
                      className={`max-w-[80%] rounded-[1.6rem] px-4 py-3 text-sm leading-6 ${
                        message.role === "user"
                          ? "bg-sky-950 text-white shadow-[0_12px_28px_rgba(12,74,110,0.16)]"
                          : "border border-[var(--blue-line)] bg-white text-slate-800"
                      }`}
                    >
                      {editingMessageId === message.message_id ? (
                        <div className="space-y-2">
                          <Textarea
                            className="min-h-[110px] bg-white text-slate-950"
                            onChange={(event) => setMessageDraft(event.target.value)}
                            value={messageDraft}
                          />
                          <div className="flex flex-wrap gap-2">
                            <Button
                              disabled={!messageDraft.trim() || updateMessageMutation.isPending}
                              onClick={() => {
                                if (message.message_id) {
                                  updateMessageMutation.mutate({
                                    messageId: message.message_id,
                                    content: messageDraft.trim(),
                                  })
                                }
                              }}
                              size="sm"
                            >
                              <Check className="size-3.5" />
                              保存
                            </Button>
                            <Button
                              onClick={() => {
                                setEditingMessageId(null)
                                setMessageDraft("")
                              }}
                              size="sm"
                              variant="secondary"
                            >
                              <X className="size-3.5" />
                              取消
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="whitespace-pre-wrap">{message.content}</div>
                      )}
                      <div className="mt-2 flex items-center gap-2 text-[11px] opacity-60">
                        {message.role === "user" ? <User className="size-3" /> : <Cpu className="size-3" />}
                        <span>{formatTime(message.timestamp)}</span>
                        {message.sources?.length ? <span>{message.sources.length} sources</span> : null}
                        {message.evidence?.length ? <span>{message.evidence.length} evidence</span> : null}
                      </div>
                      {message.role === "user" && message.message_id && editingMessageId !== message.message_id ? (
                        <div className="mt-2 flex justify-end gap-2">
                          <Button
                            className="bg-white/10 text-white hover:bg-white/20"
                            onClick={() => {
                              setEditingMessageId(message.message_id || null)
                              setMessageDraft(message.content)
                            }}
                            size="xs"
                            variant="ghost"
                          >
                            <Pencil className="size-3" />
                            编辑
                          </Button>
                          <Button
                            className="bg-white/10 text-white hover:bg-white/20"
                            disabled={regenerateMessageMutation.isPending}
                            onClick={() => regenerateMessageMutation.mutate(message)}
                            size="xs"
                            variant="ghost"
                          >
                            <RotateCcw className="size-3" />
                            重生成
                          </Button>
                        </div>
                      ) : null}
                      <MessageDiagnostics message={message} />
                    </div>
                  </div>
                ))
              )}
            </div>

            <Separator />

            <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
              <Textarea
                placeholder="输入问题，例如：请基于当前知识空间总结上下文引擎的检索链路，并指出可优化点。"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                className="min-h-[144px]"
              />
              <div className="flex flex-col justify-between gap-3 lg:w-[240px]">
                <label className="blue-panel flex cursor-pointer items-center justify-between rounded-2xl px-4 py-3">
                  <div>
                    <div className="text-sm font-medium text-slate-950">RAG retrieval</div>
                    <div className="text-xs text-slate-500">知识空间增强问答</div>
                  </div>
                  <input
                    checked={enableRag}
                    className="size-4 accent-sky-700"
                    onChange={(event) => setEnableRag(event.target.checked)}
                    type="checkbox"
                  />
                </label>

                <label className="blue-panel flex cursor-pointer items-center justify-between rounded-2xl px-4 py-3">
                  <div>
                    <div className="text-sm font-medium text-slate-950">Deep research</div>
                    <div className="text-xs text-slate-500">先评估，再进入多 Agent 流程</div>
                  </div>
                  <input
                    checked={deepResearchEnabled}
                    className="size-4 accent-sky-700"
                    onChange={(event) => {
                      const enabled = event.target.checked
                      setDeepResearchEnabled(enabled)
                      if (enabled) {
                        setEnableRag(false)
                      } else {
                        resetDeepResearchRun()
                      }
                    }}
                    type="checkbox"
                  />
                </label>

                <div className="space-y-3 rounded-2xl border border-[var(--blue-line)] bg-white p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Models</div>
                    {modelsQuery.isError ? <Badge className="bg-rose-100 text-rose-700">不可用</Badge> : null}
                  </div>
                  <label className="grid gap-1.5">
                    <span className="text-xs font-medium text-slate-600">推理模型</span>
                    <Input
                      list="chat-llm-models"
                      onChange={(event) => setSelectedLlmModel(event.target.value)}
                      placeholder={activeLlmModel ? `默认：${activeLlmModel}` : "留空使用后端默认模型"}
                      value={selectedLlmModel}
                    />
                    <datalist id="chat-llm-models">
                      {modelNames.map((name, index) => (
                        <option key={`chat-llm-${name}-${index}`} value={name} />
                      ))}
                    </datalist>
                  </label>
                  <label className="grid gap-1.5">
                    <span className="text-xs font-medium text-slate-600">Embedding 模型</span>
                    <Input
                      list="chat-embedding-models"
                      onChange={(event) => setSelectedEmbeddingModel(event.target.value)}
                      placeholder="留空使用后端默认 Embedding"
                      value={selectedEmbeddingModel}
                    />
                    <datalist id="chat-embedding-models">
                      {modelNames.map((name, index) => (
                        <option key={`chat-embedding-${name}-${index}`} value={name} />
                      ))}
                    </datalist>
                  </label>
                  <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600">
                    <div>当前推理：{activeLlmModel || "后端默认"}</div>
                    <div>当前 Embedding：{activeEmbeddingModel || "后端默认"}</div>
                  </div>
                </div>

                <div className="space-y-3 rounded-2xl border border-[var(--blue-line)] bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-slate-950">会话附件</div>
                      <div className="text-xs leading-5 text-slate-500">上传到当前知识空间后参与检索</div>
                    </div>
                    <Button
                      disabled={!selectedKnowledgeSpaceId || uploadAttachmentMutation.isPending}
                      onClick={() => attachmentInputRef.current?.click()}
                      size="icon-sm"
                      title="上传附件"
                      variant="secondary"
                    >
                      <UploadCloud className="size-4" />
                    </Button>
                    <input
                      accept=".pdf,.doc,.docx,.md,.markdown,.txt,.pptx,.xlsx,.xls,.html,.htm,.jpg,.jpeg,.png,.bmp,.webp,.tiff,.tif"
                      className="hidden"
                      onChange={(event) => {
                        const file = event.target.files?.[0]
                        if (file) {
                          uploadAttachmentMutation.mutate(file)
                        }
                        event.currentTarget.value = ""
                      }}
                      ref={attachmentInputRef}
                      type="file"
                    />
                  </div>
                  {!selectedKnowledgeSpaceId ? (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                      先在文档页选择或创建知识空间，再上传会话附件。
                    </div>
                  ) : null}
                  {activeAttachments.length > 0 ? (
                    <div className="space-y-2">
                      {activeAttachments.map((attachment) => {
                        const progress = Math.max(0, Math.min(100, Number(attachment.progress_percentage || 0)))
                        const task = taskSummary(attachment.task)
                        return (
                          <div
                            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700"
                            key={`${attachment.conversation_id}-${attachment.file_id}`}
                          >
                            <div className="flex min-w-0 items-center gap-2">
                              <Paperclip className="size-3.5 shrink-0 text-sky-700" />
                              <span className="min-w-0 flex-1 truncate font-medium text-slate-900">{attachment.filename}</span>
                              {task ? <span className="shrink-0 text-slate-500">{task}</span> : null}
                              <span className="shrink-0 text-slate-500">{attachment.status}</span>
                            </div>
                            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200">
                              <div className="h-full rounded-full bg-sky-600" style={{ width: `${progress}%` }} />
                            </div>
                            <div className="mt-1 leading-5 text-slate-500">
                              {attachment.current_stage || attachment.message || attachment.stage_details || attachment.error || "等待状态更新"}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : null}
                </div>

                <Button
                  className="h-14 rounded-2xl"
                  disabled={!prompt.trim() || sendMutation.isPending || regenerateMessageMutation.isPending || hasProcessingAttachments}
                  onClick={() => {
                    void sendMutation.mutateAsync(prompt)
                    setPrompt("")
                  }}
                  size="lg"
                >
                  <SendHorizontal className="size-4" />
                  发送消息
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Chat Notes</CardTitle>
            <CardDescription>当前实现优先打通数据链路，后面可以继续补深度研究可视化、消息编辑与中断控制。</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Badge>TanStack Router page</Badge>
            <Badge className="bg-white text-slate-700">TanStack Query cache</Badge>
            <Badge className="bg-white text-slate-700">SSE stream parser</Badge>
            <Badge className="bg-white text-slate-700">Zustand state</Badge>
            <Badge>
              <FileSearch className="mr-1 size-3" />
              backend-compatible
            </Badge>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
