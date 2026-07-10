import { useEffect, useRef } from "react"
import type { Dispatch, SetStateAction } from "react"

import { api } from "@/lib/api"
import type { ConversationAttachmentStatus, TaskDispatchInfo } from "@/types/api"

export type ChatAttachment = {
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

type UseChatAttachmentSubscriptionsOptions = {
  attachments: ChatAttachment[]
  setAttachments: Dispatch<SetStateAction<ChatAttachment[]>>
}

export function isAttachmentProcessing(status?: string | null) {
  if (!status) {
    return true
  }
  return !["completed", "failed", "cancelled"].includes(status)
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

function mergeAttachmentTask(current: ChatAttachment, task: TaskDispatchInfo, error?: string): ChatAttachment {
  return {
    ...current,
    task,
    error: error ?? current.error,
    status: task.ready && task.successful === false ? "failed" : current.status,
  }
}

export function useChatAttachmentSubscriptions({ attachments, setAttachments }: UseChatAttachmentSubscriptionsOptions) {
  const attachmentSubscriptionsRef = useRef<Record<string, () => void>>({})
  const attachmentTaskSubscriptionsRef = useRef<Record<string, () => void>>({})

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

    for (const attachment of processingAttachments) {
      const task = attachment.task
      if (task?.backend !== "celery" || !task.task_id) {
        continue
      }

      const key = `${attachment.conversation_id}:${attachment.file_id}:task`
      processingKeys.add(key)

      if (attachmentTaskSubscriptionsRef.current[key]) {
        continue
      }

      attachmentTaskSubscriptionsRef.current[key] = api.subscribeTaskStatus(
        task.task_id,
        (status) => {
          setAttachments((current) =>
            current.map((item) =>
              item.file_id === attachment.file_id && item.conversation_id === attachment.conversation_id
                ? mergeAttachmentTask(item, status)
                : item,
            ),
          )
        },
        (status) => {
          setAttachments((current) =>
            current.map((item) =>
              item.file_id === attachment.file_id && item.conversation_id === attachment.conversation_id
                ? mergeAttachmentTask(item, status)
                : item,
            ),
          )
          attachmentTaskSubscriptionsRef.current[key]?.()
          delete attachmentTaskSubscriptionsRef.current[key]
        },
        (message) => {
          setAttachments((current) =>
            current.map((item) =>
              item.file_id === attachment.file_id && item.conversation_id === attachment.conversation_id
                ? { ...item, error: message }
                : item,
            ),
          )
          attachmentTaskSubscriptionsRef.current[key]?.()
          delete attachmentTaskSubscriptionsRef.current[key]
        },
        task.backend,
      )
    }

    for (const [key, unsubscribe] of Object.entries(attachmentSubscriptionsRef.current)) {
      if (!processingKeys.has(key)) {
        unsubscribe()
        delete attachmentSubscriptionsRef.current[key]
      }
    }

    for (const [key, unsubscribe] of Object.entries(attachmentTaskSubscriptionsRef.current)) {
      if (!processingKeys.has(key)) {
        unsubscribe()
        delete attachmentTaskSubscriptionsRef.current[key]
      }
    }
  }, [attachments, setAttachments])

  useEffect(() => {
    return () => {
      for (const unsubscribe of Object.values(attachmentSubscriptionsRef.current)) {
        unsubscribe()
      }
      attachmentSubscriptionsRef.current = {}
      for (const unsubscribe of Object.values(attachmentTaskSubscriptionsRef.current)) {
        unsubscribe()
      }
      attachmentTaskSubscriptionsRef.current = {}
    }
  }, [])
}
