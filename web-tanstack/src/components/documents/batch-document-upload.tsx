import { CircleAlert, CircleCheck, Clock3, FileUp, LoaderCircle, RotateCcw, Trash2, UploadCloud, X } from "lucide-react"
import { type ChangeEvent, type DragEvent, useEffect, useRef, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import type { DocumentProgress, TaskDispatchInfo } from "@/types/api"

type UploadStatus = "queued" | "uploading" | "processing" | "completed" | "failed"

type UploadQueueItem = {
  id: string
  file: File
  status: UploadStatus
  progress: number
  documentId?: string
  serverStatus?: string
  stage?: string
  message?: string
  task?: TaskDispatchInfo | null
  error?: string
  retryable: boolean
}

type BatchDocumentUploadProps = {
  knowledgeSpaceId?: string
  onDocumentUploaded?: (documentId: string) => void
  onDocumentSettled?: (documentId: string) => void
}

const ALLOWED_EXTENSIONS = new Set([
  ".pdf",
  ".docx",
  ".doc",
  ".md",
  ".txt",
  ".markdown",
  ".pptx",
  ".xlsx",
  ".xls",
  ".html",
  ".htm",
  ".jpg",
  ".jpeg",
  ".png",
  ".bmp",
  ".webp",
  ".tiff",
  ".tif",
])
const MAX_FILE_SIZE = 200 * 1024 * 1024

function makeUploadId(file: File) {
  return `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2)}`
}

function fileExtension(file: File) {
  const index = file.name.lastIndexOf(".")
  return index >= 0 ? file.name.slice(index).toLowerCase() : ""
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

function statusLabel(status: UploadStatus) {
  switch (status) {
    case "queued":
      return "待上传"
    case "uploading":
      return "上传中"
    case "processing":
      return "处理中"
    case "completed":
      return "完成"
    case "failed":
      return "失败"
  }
}

function statusIcon(status: UploadStatus) {
  if (status === "completed") {
    return <CircleCheck className="size-3.5 text-emerald-600" />
  }
  if (status === "failed") {
    return <CircleAlert className="size-3.5 text-rose-600" />
  }
  if (status === "uploading" || status === "processing") {
    return <LoaderCircle className="size-3.5 animate-spin text-sky-700" />
  }
  return <Clock3 className="size-3.5 text-slate-500" />
}

function canStartUpload(item: UploadQueueItem) {
  return item.status === "queued" || (item.status === "failed" && item.retryable)
}

function taskProcessingMessage(task?: TaskDispatchInfo | null) {
  if (!task?.backend) {
    return undefined
  }
  if (task.backend === "celery") {
    return task.task_id ? `Celery 队列处理中 #${task.task_id.slice(0, 8)}` : "Celery 队列处理中"
  }
  if (task.backend === "fastapi-background") {
    return "本地后台处理中"
  }
  return `${task.backend} 处理中`
}

function progressMessage(progress: DocumentProgress) {
  const taskMessage = taskProcessingMessage(progress.task)
  if (progress.stage_details && taskMessage) {
    return `${progress.stage_details} (${taskMessage})`
  }
  return progress.stage_details || taskMessage
}

export function BatchDocumentUpload({ knowledgeSpaceId, onDocumentUploaded, onDocumentSettled }: BatchDocumentUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const subscriptionsRef = useRef<Map<string, () => void>>(new Map())
  const [queue, setQueue] = useState<UploadQueueItem[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [notice, setNotice] = useState<string>()

  useEffect(() => {
    const subscriptions = subscriptionsRef.current
    return () => {
      for (const unsubscribe of subscriptions.values()) {
        unsubscribe()
      }
      subscriptions.clear()
    }
  }, [])

  const updateItem = (id: string, patch: Partial<UploadQueueItem>) => {
    setQueue((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)))
  }

  const subscribeProgress = (itemId: string, documentId: string) => {
    subscriptionsRef.current.get(itemId)?.()

    const applyProgress = (progress: DocumentProgress) => {
      updateItem(itemId, {
        progress: progress.progress_percentage,
        serverStatus: progress.status,
        stage: progress.current_stage,
        message: progressMessage(progress),
        task: progress.task,
        status: progress.status === "failed" ? "failed" : "processing",
        error: progress.status === "failed" ? progress.stage_details : undefined,
        retryable: progress.status === "failed",
      })
    }

    const unsubscribe = api.subscribeDocumentProgress(
      documentId,
      applyProgress,
      (progress) => {
        applyProgress(progress)
        updateItem(itemId, {
          progress: progress.progress_percentage || 100,
          status: progress.status === "failed" ? "failed" : "completed",
          retryable: progress.status === "failed",
        })
        subscriptionsRef.current.delete(itemId)
        onDocumentSettled?.(documentId)
      },
      (message) => {
        updateItem(itemId, { message })
      },
    )

    subscriptionsRef.current.set(itemId, unsubscribe)
  }

  const addFiles = (files: File[]) => {
    setNotice(undefined)
    setQueue((current) => {
      const known = new Set(current.map((item) => `${item.file.name}:${item.file.size}`))
      const nextItems = files.map<UploadQueueItem>((file) => {
        const extension = fileExtension(file)
        const duplicateKey = `${file.name}:${file.size}`

        if (!ALLOWED_EXTENSIONS.has(extension)) {
          return {
            id: makeUploadId(file),
            file,
            status: "failed",
            progress: 0,
            error: `不支持的文件类型 ${extension || "未知"}`,
            retryable: false,
          }
        }

        if (file.size > MAX_FILE_SIZE) {
          return {
            id: makeUploadId(file),
            file,
            status: "failed",
            progress: 0,
            error: `文件超过 200MB，当前 ${formatBytes(file.size)}`,
            retryable: false,
          }
        }

        if (file.size === 0) {
          return {
            id: makeUploadId(file),
            file,
            status: "failed",
            progress: 0,
            error: "文件不能为空",
            retryable: false,
          }
        }

        if (known.has(duplicateKey)) {
          return {
            id: makeUploadId(file),
            file,
            status: "failed",
            progress: 0,
            error: "文件已在队列中",
            retryable: false,
          }
        }

        known.add(duplicateKey)
        return {
          id: makeUploadId(file),
          file,
          status: "queued",
          progress: 0,
          retryable: true,
        }
      })

      return [...current, ...nextItems]
    })
  }

  const handleFileSelect = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || [])
    if (files.length) {
      addFiles(files)
    }
    event.target.value = ""
  }

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragging(false)
    addFiles(Array.from(event.dataTransfer.files))
  }

  const removeItem = (itemId: string) => {
    subscriptionsRef.current.get(itemId)?.()
    subscriptionsRef.current.delete(itemId)
    setQueue((current) => current.filter((item) => item.id !== itemId))
  }

  const clearQueue = () => {
    for (const unsubscribe of subscriptionsRef.current.values()) {
      unsubscribe()
    }
    subscriptionsRef.current.clear()
    setQueue([])
    setNotice(undefined)
  }

  const uploadItem = async (item: UploadQueueItem) => {
    if (!knowledgeSpaceId) {
      updateItem(item.id, {
        status: "failed",
        progress: 0,
        error: "请先选择知识空间",
        retryable: true,
      })
      return false
    }

    updateItem(item.id, {
      status: "uploading",
      progress: 5,
      error: undefined,
      message: "正在上传文件",
      serverStatus: undefined,
      stage: undefined,
    })

    const result = await api.uploadDocument(knowledgeSpaceId, item.file)
    if (result.error || !result.data) {
      updateItem(item.id, {
        status: "failed",
        progress: 0,
        error: result.error || "上传失败",
        retryable: true,
      })
      return false
    }

    const documentId = result.data.document_id
    updateItem(item.id, {
      documentId,
      status: "processing",
      progress: 5,
      serverStatus: result.data.status,
      stage: "准备处理",
      message: result.data.task?.backend === "celery" ? "已投递到 Celery 队列" : "已进入后端处理队列",
      task: result.data.task,
    })
    onDocumentUploaded?.(documentId)
    subscribeProgress(item.id, documentId)
    return true
  }

  const uploadQueue = async (singleItem?: UploadQueueItem) => {
    if (!knowledgeSpaceId) {
      setNotice("请先选择知识空间")
      return
    }

    const targets = singleItem ? [singleItem] : queue.filter(canStartUpload)
    if (!targets.length) {
      return
    }

    setIsUploading(true)
    setNotice(undefined)
    let accepted = 0
    let rejected = 0

    for (const item of targets) {
      try {
        const ok = await uploadItem(item)
        if (ok) {
          accepted += 1
        } else {
          rejected += 1
        }
      } catch (error) {
        rejected += 1
        updateItem(item.id, {
          status: "failed",
          progress: 0,
          error: error instanceof Error ? error.message : "上传失败",
          retryable: true,
        })
      }
    }

    setIsUploading(false)
    setNotice(rejected > 0 ? `已投递 ${accepted} 个，失败 ${rejected} 个` : `已投递 ${accepted} 个文档`)
  }

  const counts = queue.reduce(
    (acc, item) => {
      acc[item.status] += 1
      return acc
    },
    { queued: 0, uploading: 0, processing: 0, completed: 0, failed: 0 } satisfies Record<UploadStatus, number>,
  )
  const uploadableCount = queue.filter(canStartUpload).length

  return (
    <div className="space-y-3 rounded-2xl border border-dashed border-sky-300 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-slate-950">Upload Documents</div>
          <div className="mt-1 text-xs leading-5 text-slate-500">PDF, Word, Markdown, 表格、图片等，单文件最大 200MB。</div>
        </div>
        <Badge className="bg-white text-slate-700">{queue.length} files</Badge>
      </div>

      <div
        className={`rounded-2xl border px-4 py-5 text-center transition-colors ${
          isDragging ? "border-sky-500 bg-sky-50" : "border-[var(--blue-line)] bg-[var(--surface-blue)]"
        }`}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <input
          accept={Array.from(ALLOWED_EXTENSIONS).join(",")}
          className="hidden"
          multiple
          onChange={handleFileSelect}
          ref={fileInputRef}
          type="file"
        />
        <UploadCloud className="mx-auto mb-3 size-8 text-sky-700" />
        <Button onClick={() => fileInputRef.current?.click()} variant="outline">
          <FileUp className="size-4" />
          选择文件
        </Button>
        <div className="mt-2 text-xs text-slate-500">也可以拖拽文件到这里</div>
      </div>

      {queue.length ? (
        <>
          <div className="flex flex-wrap gap-2">
            <Badge className="bg-white text-slate-700">待上传 {counts.queued}</Badge>
            <Badge className="bg-white text-slate-700">处理中 {counts.uploading + counts.processing}</Badge>
            <Badge className="bg-white text-slate-700">完成 {counts.completed}</Badge>
            <Badge className="bg-white text-slate-700">失败 {counts.failed}</Badge>
          </div>

          <div className="max-h-[360px] space-y-2 overflow-auto pr-1">
            {queue.map((item) => (
              <div className="rounded-xl border border-[var(--blue-line)] bg-white p-3" key={item.id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex min-w-0 items-center gap-2">
                      {statusIcon(item.status)}
                      <span className="truncate text-sm font-medium text-slate-950">{item.file.name}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <span>{formatBytes(item.file.size)}</span>
                      <span>{statusLabel(item.status)}</span>
                      {item.stage ? <span>{item.stage}</span> : null}
                      {item.documentId ? <span>{item.documentId.slice(0, 8)}</span> : null}
                    </div>
                  </div>

                  <div className="flex shrink-0 gap-1">
                    {item.status === "failed" && item.retryable ? (
                      <Button
                        disabled={isUploading}
                        onClick={() => uploadQueue(item)}
                        size="icon-xs"
                        title="重新上传"
                        variant="ghost"
                      >
                        <RotateCcw className="size-3" />
                      </Button>
                    ) : null}
                    <Button
                      disabled={item.status === "uploading"}
                      onClick={() => removeItem(item.id)}
                      size="icon-xs"
                      title="移除"
                      variant="ghost"
                    >
                      <X className="size-3" />
                    </Button>
                  </div>
                </div>

                <div className="mt-3 h-1.5 rounded-full bg-sky-100">
                  <div className="h-1.5 rounded-full bg-sky-600 transition-all" style={{ width: `${item.progress}%` }} />
                </div>

                {item.error || item.message ? (
                  <div
                    className={`mt-2 text-xs leading-5 ${
                      item.error ? "text-rose-700" : "text-slate-500"
                    }`}
                  >
                    {item.error || item.message}
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          {notice ? <div className="rounded-xl bg-sky-50 px-3 py-2 text-xs text-sky-800">{notice}</div> : null}

          <div className="flex flex-wrap justify-end gap-2">
            <Button disabled={isUploading} onClick={clearQueue} variant="outline">
              <Trash2 className="size-4" />
              清空
            </Button>
            <Button disabled={!uploadableCount || isUploading || !knowledgeSpaceId} onClick={() => uploadQueue()}>
              {isUploading ? <LoaderCircle className="size-4 animate-spin" /> : <FileUp className="size-4" />}
              上传 {uploadableCount}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  )
}
