import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table"
import { useVirtualizer } from "@tanstack/react-virtual"
import { useRouterState } from "@tanstack/react-router"
import { DatabaseZap, Eye, FileText, LoaderCircle, Pencil, RotateCcw, Save, Search, Trash2, X } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import { BatchDocumentUpload } from "@/components/documents/batch-document-upload"
import {
  ArtifactSourceLocatorPreview,
  SourceLocatorAnchorPreview,
} from "@/components/evidence/source-locator-preview"
import { formatSourceLocatorSummary } from "@/components/evidence/source-locator-utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"
import { useUiStore } from "@/stores/ui-store"
import type {
  DocumentChunkPreview,
  DocumentItem,
  DocumentListResponse,
  DocumentProgress,
  TaskDispatchInfo,
} from "@/types/api"

const STREAMING_DOCUMENT_STATUSES = new Set(["uploading", "processing", "parsing", "chunking", "embedding"])
const CHUNK_PAGE_SIZE = 40
const EMPTY_COUNT_RECORD: Record<string, number> = {}

const CONTENT_TYPE_LABELS: Record<string, string> = {
  all: "全部类型",
  text: "文本",
  table: "表格",
  image_ocr: "图片 OCR",
  formula: "公式",
  code: "代码",
}

const FEATURE_FILTERS = [
  { value: "all", label: "全部质量" },
  { value: "artifact_issue", label: "结构化问题" },
  { value: "table_artifact_issue", label: "表格问题" },
  { value: "ocr_artifact_issue", label: "OCR 问题" },
  { value: "table_missing_structure", label: "表格缺结构" },
  { value: "missing_anchor", label: "缺少锚点" },
  { value: "structured_missing_source_locator", label: "结构化缺定位" },
  { value: "table_missing_source", label: "表格缺来源" },
  { value: "ocr_missing_source", label: "OCR 缺来源" },
  { value: "ocr_low_confidence", label: "低置信 OCR" },
  { value: "source_locator", label: "可定位" },
  { value: "bbox_locator", label: "bbox 定位" },
  { value: "table_source_locator", label: "表格定位" },
  { value: "ocr_source_locator", label: "OCR 定位" },
  { value: "size_issue", label: "切块长度异常" },
] as const

type ChunkDeepLinkTarget = {
  documentId: string
  chunkId?: string
  chunkIndex?: number
  contentType?: string
  feature?: string
  evidenceId?: string
  contextWindow?: number
}

function parseChunkDeepLinkTarget(searchText: string): ChunkDeepLinkTarget | null {
  const params = new URLSearchParams(searchText.startsWith("?") ? searchText.slice(1) : searchText)
  const documentId = params.get("document_id")?.trim()
  if (!documentId) {
    return null
  }

  const rawChunkIndex = params.get("chunk_index")
  const chunkIndex = rawChunkIndex !== null ? Number.parseInt(rawChunkIndex, 10) : Number.NaN
  const rawContextWindow = params.get("context_window")
  const contextWindow = rawContextWindow !== null ? Number.parseInt(rawContextWindow, 10) : Number.NaN
  const contentType = params.get("content_type")?.trim()
  const feature = params.get("feature")?.trim()

  return {
    documentId,
    chunkId: params.get("chunk_id")?.trim() || undefined,
    chunkIndex: Number.isFinite(chunkIndex) && chunkIndex >= 0 ? chunkIndex : undefined,
    contentType: contentType && contentType !== "all" ? contentType : undefined,
    feature: feature && feature !== "all" ? feature : undefined,
    evidenceId: params.get("evidence_id")?.trim() || undefined,
    contextWindow: Number.isFinite(contextWindow) ? Math.max(0, Math.min(50, contextWindow)) : undefined,
  }
}

function chunkDeepLinkKey(target: ChunkDeepLinkTarget | null) {
  if (!target) {
    return ""
  }
  return [
    target.documentId,
    target.chunkId || "",
    typeof target.chunkIndex === "number" ? target.chunkIndex : "",
    target.contentType || "",
    target.feature || "",
    target.evidenceId || "",
    typeof target.contextWindow === "number" ? target.contextWindow : "",
  ].join(":")
}

function isHighlightedChunk(chunk: DocumentChunkPreview, target: ChunkDeepLinkTarget | null) {
  if (!target) {
    return false
  }
  if (target.chunkId && chunk.id === target.chunkId) {
    return true
  }
  return typeof target.chunkIndex === "number" && chunk.chunk_index === target.chunkIndex
}

function formatBytes(size: number) {
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function contentTypeLabel(value?: string | null) {
  if (!value) {
    return "未知"
  }
  return CONTENT_TYPE_LABELS[value] || value
}

function formatChunkLocation(chunk: DocumentChunkPreview) {
  const parts = []
  if (typeof chunk.page_start === "number" || typeof chunk.page === "number") {
    const start = chunk.page_start ?? chunk.page
    const end = chunk.page_end && chunk.page_end !== start ? `-${chunk.page_end}` : ""
    parts.push(`P${start}${end}`)
  }
  if (typeof chunk.token_count === "number") {
    parts.push(`${chunk.token_count} tokens`)
  }
  return parts.join(" · ") || "未定位"
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

export function DocumentsTable() {
  const queryClient = useQueryClient()
  const parentRef = useRef<HTMLDivElement>(null)
  const highlightedChunkRef = useRef<HTMLDivElement | null>(null)
  const { selectedKnowledgeSpaceId, setSelectedKnowledgeSpaceId } = useUiStore()
  const routeSearch = useRouterState({ select: (state) => state.location.searchStr })
  const [sorting, setSorting] = useState<SortingState>([])
  const [newSpaceName, setNewSpaceName] = useState("")
  const [selectedDocumentId, setSelectedDocumentId] = useState<string>()
  const [isRenaming, setIsRenaming] = useState(false)
  const [renameTitle, setRenameTitle] = useState("")
  const [chunkContentType, setChunkContentType] = useState("all")
  const [chunkFeature, setChunkFeature] = useState("all")
  const [chunkQuery, setChunkQuery] = useState("")
  const [chunkSkip, setChunkSkip] = useState(0)
  const deepLinkTarget = useMemo(() => parseChunkDeepLinkTarget(routeSearch || ""), [routeSearch])
  const deepLinkKey = useMemo(() => chunkDeepLinkKey(deepLinkTarget), [deepLinkTarget])

  const knowledgeSpacesQuery = useQuery({
    queryKey: ["knowledge-spaces"],
    queryFn: async () => {
      const result = await api.getKnowledgeSpaces()
      if (result.error) {
        throw new Error(result.error)
      }
      return result.data
    },
  })

  const documentsQuery = useQuery({
    queryKey: ["documents", selectedKnowledgeSpaceId],
    queryFn: async () => {
      const result = await api.getDocuments(selectedKnowledgeSpaceId)
      if (result.error) {
        throw new Error(result.error)
      }
      return result.data
    },
  })

  const createSpaceMutation = useMutation({
    mutationFn: async () => {
      const result = await api.createKnowledgeSpace(newSpaceName, "TanStack workspace created from the new frontend.")
      if (result.error || !result.data) {
        throw new Error(result.error || "创建知识空间失败")
      }
      return result.data
    },
    onSuccess: async (data) => {
      setNewSpaceName("")
      setSelectedKnowledgeSpaceId(data.id)
      await queryClient.invalidateQueries({ queryKey: ["knowledge-spaces"] })
    },
  })

  const data = useMemo(() => documentsQuery.data?.documents || [], [documentsQuery.data])
  const selectedDocument = useMemo(
    () => data.find((document) => document.id === selectedDocumentId),
    [data, selectedDocumentId],
  )
  const activeDeepLinkTarget = deepLinkTarget?.documentId === selectedDocumentId ? deepLinkTarget : null
  const shouldApplyDeepLinkTarget = Boolean(activeDeepLinkTarget && chunkSkip === 0)
  const selectedDocumentIsStreaming = selectedDocument ? STREAMING_DOCUMENT_STATUSES.has(selectedDocument.status) : false
  const streamingDocumentKey = useMemo(
    () =>
      data
        .filter((document) => STREAMING_DOCUMENT_STATUSES.has(document.status))
        .map((document) => document.id)
        .sort()
        .join("|"),
    [data],
  )

  useEffect(() => {
    if (deepLinkTarget?.documentId && selectedKnowledgeSpaceId) {
      setSelectedKnowledgeSpaceId(undefined)
    }
  }, [deepLinkTarget?.documentId, selectedKnowledgeSpaceId, setSelectedKnowledgeSpaceId])

  useEffect(() => {
    if (!deepLinkTarget) {
      return
    }
    setChunkContentType(deepLinkTarget.contentType || "all")
    setChunkFeature(deepLinkTarget.feature || "all")
    setChunkQuery("")
    setChunkSkip(0)
  }, [deepLinkKey, deepLinkTarget])

  useEffect(() => {
    if (!data.length) {
      if (selectedDocumentId) {
        setSelectedDocumentId(undefined)
      }
      return
    }

    if (deepLinkTarget?.documentId) {
      if (data.some((document) => document.id === deepLinkTarget.documentId)) {
        if (selectedDocumentId !== deepLinkTarget.documentId) {
          setSelectedDocumentId(deepLinkTarget.documentId)
        }
        return
      }

      if (documentsQuery.isFetching) {
        return
      }
    }

    if (!selectedDocumentId || !data.some((document) => document.id === selectedDocumentId)) {
      setSelectedDocumentId(data[0].id)
    }
  }, [data, deepLinkTarget?.documentId, documentsQuery.isFetching, selectedDocumentId])

  useEffect(() => {
    setIsRenaming(false)
    setRenameTitle(selectedDocument?.title || "")
  }, [selectedDocument?.id, selectedDocument?.title])

  useEffect(() => {
    setChunkSkip(0)
  }, [selectedDocumentId, chunkContentType, chunkFeature, chunkQuery])

  const chunkPreviewQuery = useQuery({
    queryKey: [
      "document-chunks",
      selectedDocumentId,
      chunkContentType,
      chunkFeature,
      chunkQuery,
      chunkSkip,
      shouldApplyDeepLinkTarget ? deepLinkKey : "",
    ],
    enabled: Boolean(selectedDocumentId),
    queryFn: async () => {
      const result = await api.getDocumentChunks(selectedDocumentId!, {
        skip: chunkSkip,
        limit: CHUNK_PAGE_SIZE,
        includeText: true,
        contentType: chunkContentType,
        feature: chunkFeature,
        query: chunkQuery,
        targetChunkId: shouldApplyDeepLinkTarget ? activeDeepLinkTarget?.chunkId : undefined,
        targetChunkIndex: shouldApplyDeepLinkTarget ? activeDeepLinkTarget?.chunkIndex : undefined,
        contextWindow: shouldApplyDeepLinkTarget ? activeDeepLinkTarget?.contextWindow : undefined,
      })
      if (result.error) {
        throw new Error(result.error)
      }
      return result.data
    },
  })

  const chunkPreview = chunkPreviewQuery.data
  const parseQuality = chunkPreview?.parse_quality || selectedDocument?.parse_quality || null
  const effectiveChunkSkip = chunkPreview?.skip ?? chunkSkip
  const contentTypeCounts = useMemo(
    () => chunkPreview?.facets?.content_type_counts || parseQuality?.content_type_counts || EMPTY_COUNT_RECORD,
    [chunkPreview?.facets?.content_type_counts, parseQuality?.content_type_counts],
  )
  const featureCounts = useMemo(
    () => chunkPreview?.facets?.feature_counts || EMPTY_COUNT_RECORD,
    [chunkPreview?.facets?.feature_counts],
  )
  const chunkTotal = chunkPreview?.total_chunks || 0
  const chunkEnd = Math.min(effectiveChunkSkip + CHUNK_PAGE_SIZE, chunkTotal)
  const chunkRows = useMemo(() => chunkPreview?.chunks || [], [chunkPreview?.chunks])
  const deepLinkTargetMissing = Boolean(
    activeDeepLinkTarget &&
      chunkPreview?.target_found === false &&
      (activeDeepLinkTarget.chunkId || typeof activeDeepLinkTarget.chunkIndex === "number"),
  )
  const contentTypeOptions = useMemo(() => {
    const values = new Set(["all", "text", "table", "image_ocr", "formula", "code", ...Object.keys(contentTypeCounts)])
    return Array.from(values)
  }, [contentTypeCounts])

  const patchDocumentInCache = (documentId: string, patch: Partial<DocumentItem>) => {
    queryClient.setQueryData<DocumentListResponse>(["documents", selectedKnowledgeSpaceId], (existing) => {
      if (!existing) {
        return existing
      }

      return {
        ...existing,
        documents: existing.documents.map((document) =>
          document.id === documentId ? { ...document, ...patch } : document,
        ),
      }
    })
  }

  const updateDocumentMutation = useMutation({
    mutationFn: async ({ documentId, title }: { documentId: string; title: string }) => {
      const result = await api.updateDocument(documentId, { title })
      if (result.error) {
        throw new Error(result.error)
      }
      return { documentId, title }
    },
    onSuccess: async ({ documentId, title }) => {
      patchDocumentInCache(documentId, { title })
      setIsRenaming(false)
      await queryClient.invalidateQueries({ queryKey: ["documents", selectedKnowledgeSpaceId] })
    },
  })

  const deleteDocumentMutation = useMutation({
    mutationFn: async (documentId: string) => {
      const result = await api.deleteDocument(documentId)
      if (result.error) {
        throw new Error(result.error)
      }
      return documentId
    },
    onSuccess: async (documentId) => {
      queryClient.setQueryData<DocumentListResponse>(["documents", selectedKnowledgeSpaceId], (existing) => {
        if (!existing) {
          return existing
        }

        return {
          ...existing,
          documents: existing.documents.filter((document) => document.id !== documentId),
          total: Math.max(0, existing.total - 1),
        }
      })
      queryClient.removeQueries({ queryKey: ["document-chunks", documentId] })
      if (selectedDocumentId === documentId) {
        setSelectedDocumentId(undefined)
      }
      await queryClient.invalidateQueries({ queryKey: ["documents", selectedKnowledgeSpaceId] })
    },
  })

  const retryDocumentMutation = useMutation({
    mutationFn: async (documentId: string) => {
      const result = await api.retryDocumentProcessing(documentId)
      if (result.error) {
        throw new Error(result.error)
      }
      return { documentId, task: result.data?.task }
    },
    onSuccess: async ({ documentId, task }) => {
      const patch: Partial<DocumentItem> = {
        status: "processing",
        progress_percentage: 0,
        current_stage: "重新处理",
        stage_details: "已重新投递处理任务",
      }
      if (task) {
        patch.task = task
      }
      patchDocumentInCache(documentId, patch)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents", selectedKnowledgeSpaceId] }),
        queryClient.invalidateQueries({ queryKey: ["document-chunks", documentId] }),
      ])
    },
  })

  const trimmedRenameTitle = renameTitle.trim()
  const canSubmitRename = Boolean(
    selectedDocument &&
      trimmedRenameTitle &&
      trimmedRenameTitle !== selectedDocument.title &&
      !updateDocumentMutation.isPending,
  )

  const submitRename = () => {
    if (!selectedDocument || !canSubmitRename) {
      return
    }
    updateDocumentMutation.mutate({ documentId: selectedDocument.id, title: trimmedRenameTitle })
  }

  const openDocumentPreview = (documentId: string, page?: number | null) => {
    window.open(api.documentPreviewUrl(documentId, page), "_blank", "noopener,noreferrer")
  }

  const retrySelectedDocument = () => {
    if (!selectedDocument || selectedDocumentIsStreaming) {
      return
    }
    retryDocumentMutation.mutate(selectedDocument.id)
  }

  const deleteSelectedDocument = () => {
    if (!selectedDocument) {
      return
    }

    const confirmed = window.confirm(`确认删除「${selectedDocument.title}」吗？这会清理文档记录、切块和向量数据。`)
    if (!confirmed) {
      return
    }

    deleteDocumentMutation.mutate(selectedDocument.id)
  }

  const handleUploadedDocument = (documentId: string) => {
    setSelectedDocumentId(documentId)
    void queryClient.invalidateQueries({ queryKey: ["documents", selectedKnowledgeSpaceId] })
  }

  const handleSettledDocument = (documentId: string) => {
    void queryClient.invalidateQueries({ queryKey: ["documents", selectedKnowledgeSpaceId] })
    void queryClient.invalidateQueries({ queryKey: ["document-chunks", documentId] })
  }

  useEffect(() => {
    const documentIds = streamingDocumentKey ? streamingDocumentKey.split("|") : []
    if (!documentIds.length) {
      return
    }

    const updateDocumentProgress = (progress: DocumentProgress) => {
      queryClient.setQueryData<DocumentListResponse>(["documents", selectedKnowledgeSpaceId], (existing) => {
        if (!existing) {
          return existing
        }

        return {
          ...existing,
          documents: existing.documents.map((document) =>
            document.id === progress.document_id
              ? {
                  ...document,
                  status: progress.status,
                  progress_percentage: progress.progress_percentage,
                  current_stage: progress.current_stage,
                  stage_details: progress.stage_details,
                  task: progress.task ?? document.task,
                }
              : document,
          ),
        }
      })
    }

    const unsubscribers = documentIds.map((documentId) =>
      api.subscribeDocumentProgress(
        documentId,
        updateDocumentProgress,
        (progress) => {
          updateDocumentProgress(progress)
          void queryClient.invalidateQueries({ queryKey: ["documents", selectedKnowledgeSpaceId] })
        },
        () => {
          void queryClient.invalidateQueries({ queryKey: ["documents", selectedKnowledgeSpaceId] })
        },
      ),
    )

    return () => {
      for (const unsubscribe of unsubscribers) {
        unsubscribe()
      }
    }
  }, [queryClient, selectedKnowledgeSpaceId, streamingDocumentKey])

  useEffect(() => {
    if (!activeDeepLinkTarget || chunkPreviewQuery.isFetching) {
      return
    }
    if (!chunkRows.some((chunk) => isHighlightedChunk(chunk, activeDeepLinkTarget))) {
      return
    }

    const timeout = window.setTimeout(() => {
      highlightedChunkRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
    }, 80)

    return () => window.clearTimeout(timeout)
  }, [activeDeepLinkTarget, chunkPreviewQuery.isFetching, chunkRows])

  const columns = useMemo(
    () => [
      {
        accessorKey: "title",
        header: "Title",
        cell: ({ row }: { row: { original: DocumentItem } }) => (
          <div>
            <div className="font-medium text-slate-950">{row.original.title}</div>
            <div className="text-xs text-slate-500">{row.original.file_type.toUpperCase()}</div>
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }: { row: { original: DocumentItem } }) => (
          <Badge className="bg-white text-slate-700">{row.original.status}</Badge>
        ),
      },
      {
        accessorKey: "progress_percentage",
        header: "Progress",
        cell: ({ row }: { row: { original: DocumentItem } }) => {
          const task = taskSummary(row.original.task)

          return (
            <div className="min-w-[140px]">
              <div className="mb-1 flex justify-between text-xs text-slate-500">
                <span>{row.original.current_stage || "queued"}</span>
                <span>{row.original.progress_percentage || 0}%</span>
              </div>
              <div className="h-2 rounded-full bg-sky-100">
                <div
                  className="h-2 rounded-full bg-sky-600 transition-all"
                  style={{ width: `${row.original.progress_percentage || 0}%` }}
                />
              </div>
              {task ? <div className="mt-1 text-[11px] text-slate-500">{task}</div> : null}
            </div>
          )
        },
      },
      {
        accessorKey: "file_size",
        header: "Size",
        cell: ({ row }: { row: { original: DocumentItem } }) => formatBytes(row.original.file_size),
      },
      {
        accessorKey: "created_at",
        header: "Created",
        cell: ({ row }: { row: { original: DocumentItem } }) =>
          new Intl.DateTimeFormat("zh-CN", {
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          }).format(new Date(row.original.created_at)),
      },
    ],
    [],
  )

  // TanStack Table returns rich instance methods; keeping it un-memoized here is intentional.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  const rows = table.getRowModel().rows

  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    estimateSize: () => 84,
    getScrollElement: () => parentRef.current,
    overscan: 8,
  })
  const errors = [
    knowledgeSpacesQuery.error instanceof Error ? `知识空间加载失败：${knowledgeSpacesQuery.error.message}` : null,
    documentsQuery.error instanceof Error ? `文档列表加载失败：${documentsQuery.error.message}` : null,
    createSpaceMutation.error instanceof Error ? `知识空间创建失败：${createSpaceMutation.error.message}` : null,
    updateDocumentMutation.error instanceof Error ? `重命名失败：${updateDocumentMutation.error.message}` : null,
    deleteDocumentMutation.error instanceof Error ? `删除失败：${deleteDocumentMutation.error.message}` : null,
    retryDocumentMutation.error instanceof Error ? `重试失败：${retryDocumentMutation.error.message}` : null,
    chunkPreviewQuery.error instanceof Error ? `Chunk inspector 加载失败：${chunkPreviewQuery.error.message}` : null,
  ].filter(Boolean) as string[]

  return (
    <div className="grid gap-5 xl:grid-cols-[340px_minmax(0,1fr)]">
      <Card>
        <CardHeader>
          <CardTitle>Knowledge Spaces</CardTitle>
          <CardDescription>左侧是工作空间选择和上传入口，右侧是 TanStack Table + Virtual 的文档视图。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {errors.length > 0 ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {errors.map((error) => (
                <div key={error}>{error}</div>
              ))}
            </div>
          ) : null}

          <div className="space-y-2">
            <button
              className={`w-full rounded-2xl border p-3 text-left transition-all focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-sky-100 ${
                !selectedKnowledgeSpaceId
                  ? "border-sky-950 bg-sky-950 text-white shadow-[0_12px_24px_rgba(12,74,110,0.16)]"
                  : "border-[var(--blue-line)] bg-white text-slate-700 hover:bg-[var(--surface-blue)] hover:text-sky-950"
              }`}
              onClick={() => setSelectedKnowledgeSpaceId(undefined)}
              type="button"
            >
              <div className="font-medium">全部知识空间</div>
              <div className="mt-1 text-xs opacity-70">用于跨空间检索文档和承接证据深链</div>
            </button>
            {(knowledgeSpacesQuery.data?.knowledge_spaces || []).map((space) => (
              <button
                key={space.id}
                className={`w-full rounded-2xl border p-3 text-left transition-all focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-sky-100 ${
                  selectedKnowledgeSpaceId === space.id
                    ? "border-sky-950 bg-sky-950 text-white shadow-[0_12px_24px_rgba(12,74,110,0.16)]"
                    : "border-[var(--blue-line)] bg-white text-slate-700 hover:bg-[var(--surface-blue)] hover:text-sky-950"
                }`}
                onClick={() => setSelectedKnowledgeSpaceId(space.id)}
                type="button"
              >
                <div className="font-medium">{space.name}</div>
                <div className="mt-1 text-xs opacity-70">{space.collection_name}</div>
              </button>
            ))}
          </div>

          <div className="space-y-3 rounded-2xl border border-[var(--blue-line)] bg-[var(--surface-blue)] p-4">
            <div className="text-sm font-medium text-slate-950">Create Space</div>
            <Input
              placeholder="例如：context-engine-lab"
              value={newSpaceName}
              onChange={(event) => setNewSpaceName(event.target.value)}
            />
            <Button
              className="w-full"
              disabled={!newSpaceName.trim() || createSpaceMutation.isPending}
              onClick={() => createSpaceMutation.mutate()}
            >
              <DatabaseZap className="size-4" />
              创建知识空间
            </Button>
          </div>

          <BatchDocumentUpload
            knowledgeSpaceId={selectedKnowledgeSpaceId}
            onDocumentSettled={handleSettledDocument}
            onDocumentUploaded={handleUploadedDocument}
          />
        </CardContent>
      </Card>

      <div className="grid gap-5">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle>Document Inventory</CardTitle>
                <CardDescription>虚拟滚动表格适合后续接大规模文档列表，这里先把字段和交互框好。</CardDescription>
              </div>
              <div className="flex gap-2">
                <Badge>{rows.length} rows</Badge>
                <Badge>{selectedKnowledgeSpaceId ? "space selected" : "all spaces"}</Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {selectedDocument ? (
              <div className="mb-4 flex flex-col gap-3 border-b border-[var(--blue-line)] pb-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <div className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Selected document</div>
                  {isRenaming ? (
                    <Input
                      className="mt-2 h-9 max-w-xl"
                      onChange={(event) => setRenameTitle(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          submitRename()
                        }
                        if (event.key === "Escape") {
                          setIsRenaming(false)
                          setRenameTitle(selectedDocument.title)
                        }
                      }}
                      value={renameTitle}
                    />
                  ) : (
                    <div className="mt-1 truncate text-base font-semibold text-slate-950">{selectedDocument.title}</div>
                  )}
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span>{selectedDocument.file_type.toUpperCase()}</span>
                    <span>{formatBytes(selectedDocument.file_size)}</span>
                    <span>{selectedDocument.status}</span>
                    {selectedDocument.current_stage ? <span>{selectedDocument.current_stage}</span> : null}
                    {selectedDocument.task ? <span>{taskSummary(selectedDocument.task)}</span> : null}
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {isRenaming ? (
                    <>
                      <Button disabled={!canSubmitRename} onClick={submitRename} size="sm">
                        {updateDocumentMutation.isPending ? (
                          <LoaderCircle className="size-3.5 animate-spin" />
                        ) : (
                          <Save className="size-3.5" />
                        )}
                        保存
                      </Button>
                      <Button
                        onClick={() => {
                          setIsRenaming(false)
                          setRenameTitle(selectedDocument.title)
                        }}
                        size="sm"
                        variant="outline"
                      >
                        <X className="size-3.5" />
                        取消
                      </Button>
                    </>
                  ) : (
                    <Button
                      onClick={() => {
                        setRenameTitle(selectedDocument.title)
                        setIsRenaming(true)
                      }}
                      size="sm"
                      variant="outline"
                    >
                      <Pencil className="size-3.5" />
                      重命名
                    </Button>
                  )}

                  <Button onClick={() => openDocumentPreview(selectedDocument.id)} size="sm" variant="outline">
                    <Eye className="size-3.5" />
                    预览
                  </Button>
                  <Button
                    disabled={selectedDocumentIsStreaming || retryDocumentMutation.isPending}
                    onClick={retrySelectedDocument}
                    size="sm"
                    variant="outline"
                  >
                    {retryDocumentMutation.isPending ? (
                      <LoaderCircle className="size-3.5 animate-spin" />
                    ) : (
                      <RotateCcw className="size-3.5" />
                    )}
                    重试处理
                  </Button>
                  <Button
                    disabled={deleteDocumentMutation.isPending}
                    onClick={deleteSelectedDocument}
                    size="sm"
                    variant="destructive"
                  >
                    {deleteDocumentMutation.isPending ? (
                      <LoaderCircle className="size-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="size-3.5" />
                    )}
                    删除
                  </Button>
                </div>
              </div>
            ) : null}

            <div className="overflow-x-auto rounded-2xl border border-[var(--blue-line)] bg-white">
              <div className="min-w-[820px]">
                <div className="grid grid-cols-[2fr_1fr_1.5fr_1fr_1fr] gap-4 border-b border-[var(--blue-line)] bg-[var(--surface-blue)] px-4 py-3 text-xs uppercase tracking-[0.16em] text-slate-500">
                  {table.getFlatHeaders().map((header) => (
                    <button
                      key={header.id}
                      className="text-left transition-colors hover:text-sky-900 focus-visible:outline-none focus-visible:text-sky-900"
                      onClick={header.column.getToggleSortingHandler()}
                      type="button"
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </button>
                  ))}
                </div>

                <div className="h-[520px] overflow-auto" ref={parentRef}>
                  <div
                    style={{
                      height: `${rowVirtualizer.getTotalSize()}px`,
                      position: "relative",
                    }}
                  >
                    {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                      const row = rows[virtualRow.index]
                      return (
                        <button
                          key={row.id}
                          className={`grid appearance-none grid-cols-[2fr_1fr_1.5fr_1fr_1fr] gap-4 border-0 border-b border-sky-100 px-4 py-4 text-left text-sm transition-colors ${
                            row.original.id === selectedDocumentId
                              ? "bg-sky-50 text-sky-950"
                              : "bg-white text-slate-700 hover:bg-[var(--surface-blue)]"
                          }`}
                          onClick={() => setSelectedDocumentId(row.original.id)}
                          style={{
                            position: "absolute",
                            top: 0,
                            left: 0,
                            width: "100%",
                            transform: `translateY(${virtualRow.start}px)`,
                          }}
                          type="button"
                        >
                          {row.getVisibleCells().map((cell) => (
                            <div key={cell.id} className="flex items-center">
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </div>
                          ))}
                        </button>
                      )
                    })}
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle>Chunk Inspector</CardTitle>
                <CardDescription>{selectedDocument?.title || "未选择文档"}</CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge>{selectedDocument?.status || "idle"}</Badge>
                <Badge className="bg-white text-slate-700">{chunkTotal} chunks</Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {!selectedDocument ? (
              <div className="blue-panel flex min-h-[220px] items-center justify-center rounded-2xl px-6 py-10 text-sm text-slate-500">
                暂无文档
              </div>
            ) : (
              <>
                {activeDeepLinkTarget ? (
                  <div className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
                    <div className="font-medium">
                      已从链接定位到文档
                      {activeDeepLinkTarget.evidenceId ? ` · 证据 ${activeDeepLinkTarget.evidenceId}` : ""}
                    </div>
                    <div className="mt-1 text-xs leading-5 text-sky-800">
                      {activeDeepLinkTarget.chunkId ? `chunk ${activeDeepLinkTarget.chunkId}` : null}
                      {activeDeepLinkTarget.chunkId && typeof activeDeepLinkTarget.chunkIndex === "number" ? " · " : ""}
                      {typeof activeDeepLinkTarget.chunkIndex === "number" ? `索引 ${activeDeepLinkTarget.chunkIndex}` : null}
                      {typeof activeDeepLinkTarget.contextWindow === "number"
                        ? ` · 上下文窗口 ${activeDeepLinkTarget.contextWindow}`
                        : ""}
                    </div>
                  </div>
                ) : null}

                {deepLinkTargetMissing ? (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    目标 chunk 未在当前筛选结果中找到。已加载同一文档的可用 chunk，可尝试切换质量筛选或清空搜索条件。
                  </div>
                ) : null}

                <div className="grid gap-3 md:grid-cols-4">
                  <div className="rounded-2xl border border-[var(--blue-line)] bg-white p-4">
                    <div className="text-xs uppercase tracking-[0.14em] text-slate-500">Quality</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-950">
                      {typeof parseQuality?.quality_score === "number" ? parseQuality.quality_score : "N/A"}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-[var(--blue-line)] bg-white p-4">
                    <div className="text-xs uppercase tracking-[0.14em] text-slate-500">Tables</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-950">{parseQuality?.table_count || 0}</div>
                  </div>
                  <div className="rounded-2xl border border-[var(--blue-line)] bg-white p-4">
                    <div className="text-xs uppercase tracking-[0.14em] text-slate-500">OCR</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-950">
                      {parseQuality?.ocr_recognized_images || 0}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-[var(--blue-line)] bg-white p-4">
                    <div className="text-xs uppercase tracking-[0.14em] text-slate-500">Problems</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-950">
                      {chunkPreview?.facets?.problem_chunk_count || 0}
                    </div>
                  </div>
                </div>

                <div className="grid gap-3 lg:grid-cols-[180px_220px_minmax(0,1fr)]">
                  <select
                    className="h-10 rounded-lg border border-[var(--blue-line)] bg-white px-3 text-sm text-slate-700 outline-none focus:border-sky-400 focus:ring-3 focus:ring-sky-100"
                    onChange={(event) => setChunkContentType(event.target.value)}
                    value={chunkContentType}
                  >
                    {contentTypeOptions.map((value) => (
                      <option key={value} value={value}>
                        {contentTypeLabel(value)}
                        {value === "all" ? "" : ` (${contentTypeCounts[value] || 0})`}
                      </option>
                    ))}
                  </select>

                  <select
                    className="h-10 rounded-lg border border-[var(--blue-line)] bg-white px-3 text-sm text-slate-700 outline-none focus:border-sky-400 focus:ring-3 focus:ring-sky-100"
                    onChange={(event) => setChunkFeature(event.target.value)}
                    value={chunkFeature}
                  >
                    {FEATURE_FILTERS.map((filter) => (
                      <option key={filter.value} value={filter.value}>
                        {filter.label}
                        {filter.value === "all" ? "" : ` (${featureCounts[filter.value] || 0})`}
                      </option>
                    ))}
                  </select>

                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                    <Input
                      className="pl-9"
                      onChange={(event) => setChunkQuery(event.target.value)}
                      placeholder="搜索 chunk 内容"
                      value={chunkQuery}
                    />
                  </div>
                </div>

                <div className="space-y-3">
                  {chunkPreviewQuery.isFetching ? (
                    <div className="flex items-center gap-2 rounded-2xl border border-[var(--blue-line)] bg-white px-4 py-3 text-sm text-slate-500">
                      <LoaderCircle className="size-4 animate-spin" />
                      加载中
                    </div>
                  ) : null}

                  {chunkRows.length === 0 && !chunkPreviewQuery.isFetching ? (
                    <div className="blue-panel flex min-h-[180px] items-center justify-center rounded-2xl px-6 py-8 text-sm text-slate-500">
                      没有匹配的 chunk
                    </div>
                  ) : null}

                  {chunkRows.map((chunk) => {
                    const highlighted = isHighlightedChunk(chunk, activeDeepLinkTarget)
                    const sourceLocatorSummary = formatSourceLocatorSummary(chunk.source_locator)
                    return (
                      <div
                        className={`rounded-2xl border p-4 transition-colors ${
                          highlighted
                            ? "border-amber-400 bg-amber-50 ring-2 ring-amber-300"
                            : "border-[var(--blue-line)] bg-white"
                        }`}
                        key={chunk.id}
                        ref={highlighted ? highlightedChunkRef : undefined}
                      >
                        <div className="mb-3 flex flex-wrap items-center gap-2">
                          <Badge>
                            <FileText className="mr-1 size-3" />#{chunk.chunk_index ?? "-"}
                          </Badge>
                          {highlighted ? <Badge className="bg-amber-100 text-amber-800">目标证据</Badge> : null}
                          <Badge className="bg-white text-slate-700">{contentTypeLabel(chunk.content_type)}</Badge>
                          <Badge className="bg-white text-slate-700">{formatChunkLocation(chunk)}</Badge>
                          {chunk.artifact_quality?.status === "warn" ? (
                            <Badge className="border-amber-200 bg-amber-50 text-amber-800">artifact warn</Badge>
                          ) : null}
                          <Button
                            className="ml-auto"
                            onClick={() =>
                              openDocumentPreview(chunk.document_id || selectedDocument.id, chunk.page_start ?? chunk.page)
                            }
                            size="xs"
                            variant="ghost"
                          >
                            <Eye className="size-3" />
                            原文
                          </Button>
                        </div>

                        <div className="max-h-[180px] overflow-auto whitespace-pre-wrap text-sm leading-6 text-slate-700">
                          {chunk.preview || chunk.text}
                        </div>

                        {sourceLocatorSummary ? (
                          <div className="mt-3 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
                            来源定位：{sourceLocatorSummary}
                          </div>
                        ) : null}
                        <SourceLocatorAnchorPreview locator={chunk.source_locator} />

                        {chunk.quality_notes?.length ? (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {chunk.quality_notes.map((note) => (
                              <span
                                className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs text-amber-800"
                                key={note}
                              >
                                {note}
                              </span>
                            ))}
                          </div>
                        ) : null}

                        {chunk.artifact?.type === "table" && chunk.artifact.rows?.length ? (
                          <div className="mt-4 overflow-x-auto rounded-xl border border-sky-100">
                            <table className="min-w-full text-left text-xs text-slate-600">
                              {chunk.artifact.headers?.length ? (
                                <thead className="bg-[var(--surface-blue)] text-slate-700">
                                  <tr>
                                    {chunk.artifact.headers.map((header) => (
                                      <th className="px-3 py-2 font-medium" key={header}>
                                        {header}
                                      </th>
                                    ))}
                                  </tr>
                                </thead>
                              ) : null}
                              <tbody>
                                {chunk.artifact.rows.slice(0, 4).map((row, rowIndex) => (
                                  <tr className="border-t border-sky-100" key={`${chunk.id}-${rowIndex}`}>
                                    {row.map((cell, cellIndex) => (
                                      <td className="px-3 py-2" key={`${chunk.id}-${rowIndex}-${cellIndex}`}>
                                        {cell}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : null}
                        <ArtifactSourceLocatorPreview artifact={chunk.artifact} />
                      </div>
                    )
                  })}
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm text-slate-500">
                    {chunkTotal > 0 ? `${effectiveChunkSkip + 1}-${chunkEnd} / ${chunkTotal}` : "0 / 0"}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      disabled={effectiveChunkSkip <= 0 || chunkPreviewQuery.isFetching}
                      onClick={() => setChunkSkip(Math.max(0, effectiveChunkSkip - CHUNK_PAGE_SIZE))}
                      variant="outline"
                    >
                      上一页
                    </Button>
                    <Button
                      disabled={chunkEnd >= chunkTotal || chunkPreviewQuery.isFetching}
                      onClick={() => setChunkSkip(effectiveChunkSkip + CHUNK_PAGE_SIZE)}
                      variant="outline"
                    >
                      下一页
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
