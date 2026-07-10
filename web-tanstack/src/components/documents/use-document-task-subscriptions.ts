import { useEffect, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { DocumentItem, DocumentListResponse, DocumentProgress, TaskDispatchInfo } from "@/types/api"

export const STREAMING_DOCUMENT_STATUSES = new Set(["uploading", "processing", "parsing", "chunking", "embedding"])

type UseDocumentTaskSubscriptionsOptions = {
  documents: DocumentItem[]
  selectedKnowledgeSpaceId?: string
}

export function useDocumentTaskSubscriptions({
  documents,
  selectedKnowledgeSpaceId,
}: UseDocumentTaskSubscriptionsOptions) {
  const queryClient = useQueryClient()
  const streamingDocumentKey = useMemo(
    () =>
      documents
        .filter((document) => STREAMING_DOCUMENT_STATUSES.has(document.status))
        .map((document) => document.id)
        .sort()
        .join("|"),
    [documents],
  )
  const streamingTaskKey = useMemo(
    () =>
      documents
        .filter((document) => {
          const task = document.task
          return (
            task?.backend === "celery" &&
            Boolean(task.task_id) &&
            (STREAMING_DOCUMENT_STATUSES.has(document.status) || task.ready === false)
          )
        })
        .map((document) => `${document.id}::${document.task?.backend}::${document.task?.task_id}`)
        .sort()
        .join("|"),
    [documents],
  )

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
    const taskEntries = streamingTaskKey
      ? streamingTaskKey.split("|").map((entry) => {
          const [documentId, backend, taskId] = entry.split("::")
          return { backend, documentId, taskId }
        })
      : []

    if (!taskEntries.length) {
      return
    }

    const updateDocumentTaskStatus = (documentId: string, task: TaskDispatchInfo) => {
      queryClient.setQueryData<DocumentListResponse>(["documents", selectedKnowledgeSpaceId], (existing) => {
        if (!existing) {
          return existing
        }

        const failed = task.ready && task.successful === false
        return {
          ...existing,
          documents: existing.documents.map((document) =>
            document.id === documentId
              ? {
                  ...document,
                  task,
                  ...(failed
                    ? {
                        status: "failed",
                        current_stage: "后台任务失败",
                        stage_details: task.error || "Celery 任务执行失败",
                      }
                    : {}),
                }
              : document,
          ),
        }
      })
    }

    const unsubscribers = taskEntries.map(({ backend, documentId, taskId }) =>
      api.subscribeTaskStatus(
        taskId,
        (task) => updateDocumentTaskStatus(documentId, task),
        (task) => {
          updateDocumentTaskStatus(documentId, task)
          void queryClient.invalidateQueries({ queryKey: ["documents", selectedKnowledgeSpaceId] })
          if (task.successful !== false) {
            void queryClient.invalidateQueries({ queryKey: ["document-chunks", documentId] })
          }
        },
        undefined,
        backend,
      ),
    )

    return () => {
      for (const unsubscribe of unsubscribers) {
        unsubscribe()
      }
    }
  }, [queryClient, selectedKnowledgeSpaceId, streamingTaskKey])
}
