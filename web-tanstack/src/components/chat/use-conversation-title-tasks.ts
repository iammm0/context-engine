import { useEffect, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { ConversationDetail, ConversationListResponse, TaskDispatchInfo } from "@/types/api"

type ConversationSummary = ConversationListResponse["conversations"][number]

type UseConversationTitleTasksOptions = {
  activeConversationId?: string | null
  conversations?: ConversationSummary[] | null
}

function readGeneratedTitle(task: TaskDispatchInfo): string | null {
  const title = task.result?.title
  return typeof title === "string" && title.trim() ? title.trim() : null
}

export function useConversationTitleTasks({ activeConversationId, conversations }: UseConversationTitleTasksOptions) {
  const queryClient = useQueryClient()
  const titleTaskKey = useMemo(
    () =>
      (conversations || [])
        .filter((conversation) => {
          const task = conversation.title_task
          return task?.backend === "celery" && Boolean(task.task_id) && task.ready === false
        })
        .map((conversation) => `${conversation.id}::${conversation.title_task?.backend}::${conversation.title_task?.task_id}`)
        .sort()
        .join("|"),
    [conversations],
  )

  useEffect(() => {
    const taskEntries = titleTaskKey
      ? titleTaskKey.split("|").map((entry) => {
          const [conversationId, backend, taskId] = entry.split("::")
          return { backend, conversationId, taskId }
        })
      : []

    if (!taskEntries.length) {
      return
    }

    const updateTitleTask = (conversationId: string, task: TaskDispatchInfo) => {
      const generatedTitle = readGeneratedTitle(task)
      queryClient.setQueryData<ConversationListResponse>(["conversations"], (existing) => {
        if (!existing) {
          return existing
        }

        return {
          ...existing,
          conversations: existing.conversations.map((conversation) =>
            conversation.id === conversationId
              ? {
                  ...conversation,
                  title: generatedTitle || conversation.title,
                  title_task: task,
                }
              : conversation,
          ),
        }
      })

      queryClient.setQueryData<ConversationDetail>(["conversation", conversationId], (existing) =>
        existing
          ? {
              ...existing,
              title: generatedTitle || existing.title,
              title_task: task,
            }
          : existing,
      )
    }

    const unsubscribers = taskEntries.map(({ backend, conversationId, taskId }) =>
      api.subscribeTaskStatus(
        taskId,
        (task) => updateTitleTask(conversationId, task),
        (task) => {
          updateTitleTask(conversationId, task)
          void queryClient.invalidateQueries({ queryKey: ["conversations"] })
          if (conversationId === activeConversationId) {
            void queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] })
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
  }, [activeConversationId, queryClient, titleTaskKey])
}
