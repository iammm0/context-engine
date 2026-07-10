import { useCallback, useEffect, useRef } from "react"
import type { Dispatch, SetStateAction } from "react"

import { api } from "@/lib/api"
import { taskProcessingMessage } from "@/lib/task"
import type { DocumentProgress, TaskDispatchInfo } from "@/types/api"

export type UploadStatus = "queued" | "uploading" | "processing" | "completed" | "failed"

export type UploadQueueItem = {
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

type UseBatchDocumentUploadProgressOptions = {
  onDocumentSettled?: (documentId: string) => void
  setQueue: Dispatch<SetStateAction<UploadQueueItem[]>>
}

function progressMessage(progress: DocumentProgress) {
  const taskMessage = taskProcessingMessage(progress.task)
  if (progress.stage_details && taskMessage) {
    return `${progress.stage_details} (${taskMessage})`
  }
  return progress.stage_details || taskMessage
}

export function useBatchDocumentUploadProgress({
  onDocumentSettled,
  setQueue,
}: UseBatchDocumentUploadProgressOptions) {
  const subscriptionsRef = useRef<Map<string, () => void>>(new Map())
  const taskSubscriptionsRef = useRef<Map<string, () => void>>(new Map())

  useEffect(() => {
    const subscriptions = subscriptionsRef.current
    const taskSubscriptions = taskSubscriptionsRef.current
    return () => {
      for (const unsubscribe of subscriptions.values()) {
        unsubscribe()
      }
      subscriptions.clear()
      for (const unsubscribe of taskSubscriptions.values()) {
        unsubscribe()
      }
      taskSubscriptions.clear()
    }
  }, [])

  const updateItem = useCallback(
    (id: string, patch: Partial<UploadQueueItem>) => {
      setQueue((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)))
    },
    [setQueue],
  )

  const stopItemSubscriptions = useCallback((itemId: string) => {
    subscriptionsRef.current.get(itemId)?.()
    subscriptionsRef.current.delete(itemId)
    taskSubscriptionsRef.current.get(itemId)?.()
    taskSubscriptionsRef.current.delete(itemId)
  }, [])

  const applyTaskStatus = useCallback(
    (itemId: string, task: TaskDispatchInfo) => {
      const taskMessage = taskProcessingMessage(task)
      if (task.ready && task.successful === false) {
        updateItem(itemId, {
          task,
          status: "failed",
          error: task.error || "后台任务执行失败",
          retryable: true,
        })
        return
      }

      updateItem(itemId, {
        task,
        message: taskMessage,
      })
    },
    [updateItem],
  )

  const subscribeTaskProgress = useCallback(
    (itemId: string, task?: TaskDispatchInfo | null) => {
      taskSubscriptionsRef.current.get(itemId)?.()
      taskSubscriptionsRef.current.delete(itemId)

      if (task?.backend !== "celery" || !task.task_id) {
        return
      }

      const unsubscribe = api.subscribeTaskStatus(
        task.task_id,
        (status) => applyTaskStatus(itemId, status),
        (status) => {
          applyTaskStatus(itemId, status)
          taskSubscriptionsRef.current.delete(itemId)
        },
        (message) => {
          updateItem(itemId, { message })
          taskSubscriptionsRef.current.delete(itemId)
        },
        task.backend,
      )
      taskSubscriptionsRef.current.set(itemId, unsubscribe)
    },
    [applyTaskStatus, updateItem],
  )

  const subscribeProgress = useCallback(
    (itemId: string, documentId: string) => {
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
          taskSubscriptionsRef.current.get(itemId)?.()
          taskSubscriptionsRef.current.delete(itemId)
          onDocumentSettled?.(documentId)
        },
        (message) => {
          updateItem(itemId, { message })
        },
      )

      subscriptionsRef.current.set(itemId, unsubscribe)
    },
    [onDocumentSettled, updateItem],
  )

  return {
    stopItemSubscriptions,
    subscribeProgress,
    subscribeTaskProgress,
    updateItem,
  }
}
