import type { TaskDispatchInfo } from "@/types/api"
import { api } from "@/lib/api"

const CELERY_STATE_LABELS: Record<string, string> = {
  PENDING: "排队中",
  PROGRESS: "运行中",
  RECEIVED: "已接收",
  STARTED: "运行中",
  RETRY: "重试中",
  SUCCESS: "成功",
  FAILURE: "失败",
  REVOKED: "已取消",
  UNKNOWN: "未知",
}

export function taskBackendLabel(task?: TaskDispatchInfo | null) {
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

export function taskStateLabel(task?: TaskDispatchInfo | null) {
  const state = task?.state?.trim()
  if (!state) {
    return null
  }
  return CELERY_STATE_LABELS[state] || state
}

export function taskSummary(task?: TaskDispatchInfo | null) {
  const backend = taskBackendLabel(task)
  if (!backend) {
    return null
  }

  const state = taskStateLabel(task)
  const taskId = task?.task_id ? `#${task.task_id.slice(0, 8)}` : null
  return [backend, state, taskId].filter(Boolean).join(" ")
}

export function taskProcessingMessage(task?: TaskDispatchInfo | null) {
  const summary = taskSummary(task)
  if (!summary) {
    return undefined
  }
  if (task?.backend === "fastapi-background") {
    return `${summary} 后台处理中`
  }
  return `${summary} 处理中`
}

export function createAbortError() {
  const error = new Error("已停止生成")
  error.name = "AbortError"
  return error
}

export function waitForTaskCompletion(
  task: TaskDispatchInfo,
  signal: AbortSignal,
  onProgress: (task: TaskDispatchInfo) => void,
): Promise<TaskDispatchInfo> {
  if (!task.task_id) {
    return Promise.reject(new Error("任务没有返回可订阅的 Celery task_id"))
  }
  const taskId = task.task_id

  return new Promise((resolve, reject) => {
    let unsubscribe: () => void = () => {}

    const cleanup = () => {
      signal.removeEventListener("abort", handleAbort)
      unsubscribe()
    }
    const handleAbort = () => {
      cleanup()
      reject(createAbortError())
    }

    signal.addEventListener("abort", handleAbort, { once: true })
    onProgress(task)

    unsubscribe = api.subscribeTaskStatus(
      taskId,
      onProgress,
      (nextTask) => {
        cleanup()
        resolve(nextTask)
      },
      (message) => {
        cleanup()
        reject(new Error(message))
      },
      task.backend,
    )

    if (signal.aborted) {
      handleAbort()
    }
  })
}
