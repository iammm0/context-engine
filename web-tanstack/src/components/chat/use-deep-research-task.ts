import { useCallback, useState } from "react"
import type { Dispatch, SetStateAction } from "react"

import { taskSummary } from "@/lib/task"
import type {
  DeepResearchAgentResult,
  DeepResearchAgentStatus,
  DeepResearchEvaluation,
  TaskDispatchInfo,
} from "@/types/api"

type StreamingMeta = {
  evidence: number
  sources: number
  status: string
}

type DeepResearchTaskResult = {
  phase?: string
  message?: string
  progress?: number
  run_id?: string
  selected_agents?: string[]
  planning?: string
  agent_statuses?: DeepResearchAgentStatus[]
  agent_results?: DeepResearchAgentResult[]
  html_content?: string
  final_content?: string
  message_id?: string | null
}

type UseDeepResearchTaskOptions = {
  buildMarkdown: (results: DeepResearchAgentResult[], htmlContent?: string) => string
  setDraftAnswer: Dispatch<SetStateAction<string>>
  setStreamingMeta: Dispatch<SetStateAction<StreamingMeta>>
}

function readDeepResearchTaskResult(task: TaskDispatchInfo): DeepResearchTaskResult | null {
  const result = task.result
  if (!result || typeof result !== "object") {
    return null
  }
  return result as DeepResearchTaskResult
}

export function useDeepResearchTask({
  buildMarkdown,
  setDraftAnswer,
  setStreamingMeta,
}: UseDeepResearchTaskOptions) {
  const [gate, setGate] = useState<DeepResearchEvaluation | null>(null)
  const [statuses, setStatuses] = useState<DeepResearchAgentStatus[]>([])
  const [results, setResults] = useState<DeepResearchAgentResult[]>([])
  const [htmlContent, setHtmlContent] = useState("")

  const reset = useCallback(() => {
    setGate(null)
    setStatuses([])
    setResults([])
    setHtmlContent("")
  }, [])

  const setInitialStatuses = useCallback((nextStatuses: DeepResearchAgentStatus[]) => {
    setStatuses(nextStatuses)
  }, [])

  const applyTaskProgress = useCallback(
    (task: TaskDispatchInfo) => {
      const result = readDeepResearchTaskResult(task)
      const taskLabel = taskSummary(task)
      if (!result) {
        setStreamingMeta({ evidence: 0, sources: 0, status: taskLabel || "Deep research task" })
        return
      }

      setStreamingMeta({
        evidence: 0,
        sources: 0,
        status: result.message || taskLabel || result.phase || "Deep research task",
      })
      if (result.planning && !gate) {
        setDraftAnswer(`## 研究规划\n\n${result.planning}`)
      }
      if (Array.isArray(result.agent_statuses)) {
        setStatuses(result.agent_statuses)
      }
      if (Array.isArray(result.agent_results)) {
        setResults(result.agent_results)
        setDraftAnswer(buildMarkdown(result.agent_results, result.html_content))
      }
      if (typeof result.html_content === "string" && result.html_content.trim()) {
        setHtmlContent(result.html_content)
      }
      if (typeof result.final_content === "string" && result.final_content.trim()) {
        setDraftAnswer(result.final_content)
      }
    },
    [buildMarkdown, gate, setDraftAnswer, setStreamingMeta],
  )

  return {
    applyTaskProgress,
    gate,
    htmlContent,
    reset,
    results,
    setGate,
    setInitialStatuses,
    statuses,
  }
}
