import type {
  AgentConfigItem,
  AgentConfigUpdate,
  AgentConfigsResponse,
  ApiEnvelope,
  ChatStreamEvent,
  DocumentChunksResponse,
  ConversationDetail,
  ConversationListResponse,
  DocumentListResponse,
  DocumentProgress,
  KnowledgeSpace,
  KnowledgeSpacesResponse,
  MessagePayload,
  ModelsResponse,
  RuntimeConfigResponse,
  RuntimeConfigUpdate,
} from "@/types/api"

type ChatPayload = {
  query: string
  conversation_id?: string
  knowledge_space_ids?: string[]
  enable_rag?: boolean
  generation_config?: Record<string, unknown>
}

type UploadDocumentResponse = {
  message?: string
  document_id: string
  filename?: string
  file_size?: number
  status: string
  task?: {
    backend: string
    task_id?: string | null
    fallback_reason?: string
  }
}

type ProgressSubscriber = (progress: DocumentProgress) => void

type DocumentChunksOptions = {
  skip?: number
  limit?: number
  includeText?: boolean
  contentType?: string
  feature?: string
  query?: string
  targetChunkId?: string
  targetChunkIndex?: number
  contextWindow?: number
}

const API_BASE_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "")

function apiUrl(path: string) {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`
}

function parseHttpError(payload: unknown): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === "string") {
      return detail
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg: unknown }).msg)
          }
          return String(item)
        })
        .join("; ")
    }
  }
  return "请求失败"
}

async function readJson<T>(response: Response): Promise<T | undefined> {
  const text = await response.text()
  if (!text) {
    return undefined
  }

  try {
    return JSON.parse(text) as T
  } catch {
    return undefined
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<ApiEnvelope<T>> {
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.headers as Record<string, string> | undefined),
      },
    })
    const payload = await readJson<unknown>(response)

    if (!response.ok) {
      return { error: parseHttpError(payload) }
    }

    return { data: payload as T }
  } catch (error) {
    return { error: error instanceof Error ? error.message : "网络错误" }
  }
}

function buildQuery(params: Record<string, string | number | boolean | undefined>) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      query.set(key, String(value))
    }
  }
  const text = query.toString()
  return text ? `?${text}` : ""
}

async function parseSseResponse(response: Response, onEvent: (event: ChatStreamEvent) => void) {
  if (!response.body) {
    throw new Error("响应流为空")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split("\n\n")
    buffer = frames.pop() || ""

    for (const frame of frames) {
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n")

      if (!data) {
        continue
      }

      onEvent(JSON.parse(data) as ChatStreamEvent)
    }
  }
}

export const api = {
  getModels() {
    return requestJson<ModelsResponse>("/api/chat/models")
  },

  getConversations() {
    return requestJson<ConversationListResponse>("/api/chat/conversations")
  },

  createConversation(title: string) {
    return requestJson<{ id: string; title: string; created_at: string; updated_at: string }>("/api/chat/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    })
  },

  getConversation(conversationId: string) {
    return requestJson<ConversationDetail>(`/api/chat/conversations/${encodeURIComponent(conversationId)}`)
  },

  addConversationMessage(conversationId: string, body: MessagePayload) {
    return requestJson<{ success?: boolean; message_id?: string; timestamp?: string }>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    )
  },

  async streamChat(body: ChatPayload, onEvent: (event: ChatStreamEvent) => void) {
    const response = await fetch(apiUrl("/api/chat/"), {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      const payload = await readJson<unknown>(response)
      throw new Error(parseHttpError(payload))
    }

    await parseSseResponse(response, onEvent)
  },

  getKnowledgeSpaces() {
    return requestJson<KnowledgeSpacesResponse>("/api/knowledge-spaces")
  },

  createKnowledgeSpace(name: string, description?: string) {
    return requestJson<KnowledgeSpace>("/api/knowledge-spaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    })
  },

  getDocuments(knowledgeSpaceId?: string) {
    return requestJson<DocumentListResponse>(
      `/api/documents${buildQuery({ skip: 0, limit: 100, knowledge_space_id: knowledgeSpaceId })}`,
    )
  },

  getDocumentChunks(documentId: string, options?: DocumentChunksOptions) {
    return requestJson<DocumentChunksResponse>(
      `/api/documents/${encodeURIComponent(documentId)}/chunks${buildQuery({
        skip: options?.skip ?? 0,
        limit: options?.limit ?? 40,
        include_text: options?.includeText ?? true,
        content_type: options?.contentType && options.contentType !== "all" ? options.contentType : undefined,
        feature: options?.feature && options.feature !== "all" ? options.feature : undefined,
        q: options?.query?.trim() || undefined,
        target_chunk_id: options?.targetChunkId,
        target_chunk_index: options?.targetChunkIndex,
        context_window: options?.contextWindow,
      })}`,
    )
  },

  async uploadDocument(knowledgeSpaceId: string, file: File): Promise<ApiEnvelope<UploadDocumentResponse>> {
    const form = new FormData()
    form.append("file", file)
    form.append("knowledge_space_id", knowledgeSpaceId)

    try {
      const response = await fetch(apiUrl("/api/documents/upload"), {
        method: "POST",
        body: form,
      })
      const payload = await readJson<unknown>(response)

      if (!response.ok) {
        return { error: parseHttpError(payload) }
      }

      return { data: payload as UploadDocumentResponse }
    } catch (error) {
      return { error: error instanceof Error ? error.message : "上传失败" }
    }
  },

  subscribeDocumentProgress(
    documentId: string,
    onProgress: ProgressSubscriber,
    onDone?: ProgressSubscriber,
    onError?: (message: string) => void,
  ) {
    const source = new EventSource(apiUrl(`/api/documents/${encodeURIComponent(documentId)}/progress/stream`))

    const handleProgress = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as DocumentProgress
      onProgress(payload)
    }

    source.addEventListener("progress", handleProgress)
    source.addEventListener("done", (event) => {
      const payload = JSON.parse((event as MessageEvent<string>).data) as DocumentProgress
      onDone?.(payload)
      source.close()
    })
    source.addEventListener("error", (event) => {
      if (source.readyState === EventSource.CLOSED) {
        return
      }
      onError?.("文档进度订阅中断")
      if ("data" in event && typeof event.data === "string" && event.data) {
        try {
          onError?.(JSON.parse(event.data).error || "文档进度订阅中断")
        } catch {
          onError?.("文档进度订阅中断")
        }
      }
    })

    return () => source.close()
  },

  getRuntimeConfig() {
    return requestJson<RuntimeConfigResponse>("/api/settings/runtime")
  },

  updateRuntimeConfig(body: RuntimeConfigUpdate) {
    return requestJson<RuntimeConfigResponse>("/api/settings/runtime", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  },

  getAgents() {
    return requestJson<AgentConfigsResponse>("/api/settings/agents")
  },

  updateAgentConfig(agentType: string, body: AgentConfigUpdate) {
    return requestJson<AgentConfigItem>(`/api/settings/agents/${encodeURIComponent(agentType)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  },
}
