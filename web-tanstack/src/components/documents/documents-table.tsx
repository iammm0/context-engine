import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table"
import { useVirtualizer } from "@tanstack/react-virtual"
import { DatabaseZap, FileUp, LoaderCircle } from "lucide-react"
import { useMemo, useRef, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"
import { useUiStore } from "@/stores/ui-store"
import type { DocumentItem } from "@/types/api"

function formatBytes(size: number) {
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export function DocumentsTable() {
  const queryClient = useQueryClient()
  const parentRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const { selectedKnowledgeSpaceId, setSelectedKnowledgeSpaceId } = useUiStore()
  const [sorting, setSorting] = useState<SortingState>([])
  const [newSpaceName, setNewSpaceName] = useState("")

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

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!selectedKnowledgeSpaceId) {
        throw new Error("请先选择一个知识空间")
      }

      const result = await api.uploadDocument(selectedKnowledgeSpaceId, file)
      if (result.error) {
        throw new Error(result.error)
      }
      return result.data
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["documents", selectedKnowledgeSpaceId] })
    },
  })

  const data = useMemo(() => documentsQuery.data?.documents || [], [documentsQuery.data])

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
        cell: ({ row }: { row: { original: DocumentItem } }) => (
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
          </div>
        ),
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
    uploadMutation.error instanceof Error ? `上传失败：${uploadMutation.error.message}` : null,
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
              placeholder="例如：advanced-rag-lab"
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

          <div className="space-y-3 rounded-2xl border border-dashed border-sky-300 bg-white p-4">
            <div className="text-sm font-medium text-slate-950">Upload Document</div>
            <div className="text-xs leading-5 text-slate-500">支持直接接现有 `/api/documents/upload`，上传后可继续轮询状态。</div>
            <input
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) {
                  uploadMutation.mutate(file)
                }
              }}
              ref={fileRef}
              type="file"
            />
            <Button className="w-full" onClick={() => fileRef.current?.click()} variant="outline">
              {uploadMutation.isPending ? <LoaderCircle className="size-4 animate-spin" /> : <FileUp className="size-4" />}
              上传文件
            </Button>
          </div>
        </CardContent>
      </Card>

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
                      <div
                        key={row.id}
                        className="grid grid-cols-[2fr_1fr_1.5fr_1fr_1fr] gap-4 border-b border-sky-100 px-4 py-4 text-sm text-slate-700"
                        style={{
                          position: "absolute",
                          top: 0,
                          left: 0,
                          width: "100%",
                          transform: `translateY(${virtualRow.start}px)`,
                        }}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <div key={cell.id} className="flex items-center">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </div>
                        ))}
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
