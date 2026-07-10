import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { api } from "@/lib/api"
import { taskSummary, waitForTaskCompletion } from "@/lib/task"
import type { QueryAnalysisResponse, TaskDispatchInfo } from "@/types/api"

type QueryAnalysisRun = {
  status: "idle" | "queued" | "running" | "completed" | "failed"
  query?: string
  task?: TaskDispatchInfo | null
  result?: QueryAnalysisResponse | null
  error?: string | null
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError"
}

function readQueryAnalysisResult(task: TaskDispatchInfo): QueryAnalysisResponse | null {
  const result = task.result
  if (!result) {
    return null
  }

  if (typeof result.need_retrieval !== "boolean" || typeof result.reason !== "string") {
    return null
  }

  return {
    need_retrieval: result.need_retrieval,
    reason: result.reason,
    confidence: typeof result.confidence === "string" ? result.confidence : "medium",
  }
}

export function useQueryAnalysisTask() {
  const [run, setRun] = useState<QueryAnalysisRun>({ status: "idle" })
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      abortRef.current = null
    }
  }, [])

  const start = useCallback(async (query: string) => {
    const normalizedQuery = query.trim()
    if (!normalizedQuery) {
      return
    }

    abortRef.current?.abort()
    const abortController = new AbortController()
    abortRef.current = abortController
    setRun({ status: "queued", query: normalizedQuery, result: null, error: null })

    try {
      const queued = await api.queueQueryAnalysis(normalizedQuery)
      if (abortController.signal.aborted) {
        return
      }
      if (queued.error || !queued.data) {
        setRun({
          status: "failed",
          query: normalizedQuery,
          result: null,
          error: queued.error || "查询分析任务投递失败",
        })
        return
      }

      const task = queued.data
      setRun({ status: "running", query: normalizedQuery, task, result: null, error: null })

      const finalTask = await waitForTaskCompletion(task, abortController.signal, (status) =>
        setRun((current) => ({
          ...current,
          status: status.ready ? current.status : "running",
          task: status,
        })),
      )
      if (abortController.signal.aborted) {
        return
      }

      const result = readQueryAnalysisResult(finalTask)
      setRun({
        status: result ? "completed" : "failed",
        query: normalizedQuery,
        task: finalTask,
        result,
        error: result ? null : finalTask.error || "查询分析任务未返回有效结果",
      })
    } catch (error) {
      if (isAbortError(error)) {
        return
      }
      setRun({
        status: "failed",
        query: normalizedQuery,
        result: null,
        error: error instanceof Error ? error.message : "查询分析任务投递失败",
      })
    } finally {
      if (abortRef.current === abortController) {
        abortRef.current = null
      }
    }
  }, [])

  const isRunning = run.status === "queued" || run.status === "running"
  const taskLabel = useMemo(() => taskSummary(run.task), [run.task])

  return {
    isRunning,
    result: run.result,
    run,
    start,
    taskLabel,
  }
}
