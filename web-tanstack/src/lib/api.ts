import type {
  AgentConfigItem,
  AgentConfigUpdate,
  AgentConfigsResponse,
  ApiEnvelope,
  ActionResponse,
  ChatRequestPayload,
  ChatStreamEvent,
  ConversationAttachmentStatus,
  ConversationAttachmentUploadResponse,
  ConversationCreateResponse,
  ConversationUpdateResponse,
  DocumentActionResponse,
  DocumentChunksResponse,
  DocumentUploadResponse,
  DeepResearchEvaluateRequest,
  DeepResearchEvaluation,
  DeepResearchRequest,
  DeepResearchStreamEvent,
  ConversationUpdate,
  ConversationDetail,
  ConversationListResponse,
  DocumentListResponse,
  DocumentProgress,
  DocumentUpdate,
  KnowledgeSpace,
  KnowledgeSpacesResponse,
  MessageActionResponse,
  MessageUpdate,
  MessagePayload,
  ModelsResponse,
  RegenerateMessageResponse,
  RuntimeConfigResponse,
  RuntimeConfigUpdate,
} from "@/types/api"

type ProgressSubscriber = (progress: DocumentProgress) => void
type AttachmentProgressSubscriber = (progress: ConversationAttachmentStatus) => void

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

async function parseSseResponse<T>(response: Response, onEvent: (event: T) => void) {
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

      onEvent(JSON.parse(data) as T)
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
    return requestJson<ConversationCreateResponse>("/api/chat/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    })
  },

  getConversation(conversationId: string) {
    return requestJson<ConversationDetail>(`/api/chat/conversations/${encodeURIComponent(conversationId)}`)
  },

  updateConversation(conversationId: string, body: ConversationUpdate) {
    return requestJson<ConversationUpdateResponse>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    )
  },

  deleteConversation(conversationId: string) {
    return requestJson<ActionResponse>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}`,
      {
        method: "DELETE",
      },
    )
  },

  addConversationMessage(conversationId: string, body: MessagePayload) {
    return requestJson<MessageActionResponse>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    )
  },

  updateConversationMessage(conversationId: string, messageId: string, body: MessageUpdate) {
    return requestJson<MessageActionResponse>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    )
  },

  regenerateConversationMessage(conversationId: string, messageId: string) {
    return requestJson<RegenerateMessageResponse>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/regenerate`,
      {
        method: "POST",
      },
    )
  },

  async streamChat(body: ChatRequestPayload, onEvent: (event: ChatStreamEvent) => void) {
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

    await parseSseResponse<ChatStreamEvent>(response, onEvent)
  },

  evaluateDeepResearch(body: DeepResearchEvaluateRequest) {
    return requestJson<DeepResearchEvaluation>("/api/chat/deep-research/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  },

  async streamDeepResearch(body: DeepResearchRequest, onEvent: (event: DeepResearchStreamEvent) => void) {
    const response = await fetch(apiUrl("/api/chat/deep-research"), {
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

    await parseSseResponse<DeepResearchStreamEvent>(response, onEvent)
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

  updateDocument(documentId: string, body: DocumentUpdate) {
    return requestJson<DocumentActionResponse>(`/api/documents/${encodeURIComponent(documentId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  },

  deleteDocument(documentId: string) {
    return requestJson<DocumentActionResponse>(`/api/documents/${encodeURIComponent(documentId)}`, {
      method: "DELETE",
    })
  },

  retryDocumentProcessing(documentId: string) {
    return requestJson<DocumentActionResponse>(`/api/documents/${encodeURIComponent(documentId)}/retry`, {
      method: "POST",
    })
  },

  documentPreviewUrl(documentId: string, page?: number | null) {
    const pageFragment = typeof page === "number" && page > 0 ? `#page=${page}` : ""
    return `${apiUrl(`/api/documents/${encodeURIComponent(documentId)}/preview`)}${pageFragment}`
  },

  async uploadDocument(knowledgeSpaceId: string, file: File): Promise<ApiEnvelope<DocumentUploadResponse>> {
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

      return { data: payload as DocumentUploadResponse }
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

  async uploadConversationAttachment(
    conversationId: string,
    knowledgeSpaceId: string,
    file: File,
  ): Promise<ApiEnvelope<ConversationAttachmentUploadResponse>> {
    const form = new FormData()
    form.append("file", file)
    form.append("conversation_id", conversationId)
    form.append("knowledge_space_id", knowledgeSpaceId)

    try {
      const response = await fetch(apiUrl("/api/chat/conversation-attachment"), {
        method: "POST",
        body: form,
      })
      const payload = await readJson<unknown>(response)

      if (!response.ok) {
        return { error: parseHttpError(payload) }
      }

      return { data: payload as ConversationAttachmentUploadResponse }
    } catch (error) {
      return { error: error instanceof Error ? error.message : "附件上传失败" }
    }
  },

  getConversationAttachmentStatus(conversationId: string, fileId: string) {
    return requestJson<ConversationAttachmentStatus>(
      `/api/chat/conversation-attachment/${encodeURIComponent(conversationId)}/${encodeURIComponent(fileId)}/status`,
    )
  },

  subscribeConversationAttachmentProgress(
    conversationId: string,
    fileId: string,
    onProgress: AttachmentProgressSubscriber,
    onDone?: AttachmentProgressSubscriber,
    onError?: (message: string) => void,
  ) {
    const source = new EventSource(
      apiUrl(
        `/api/chat/conversation-attachment/${encodeURIComponent(conversationId)}/${encodeURIComponent(fileId)}/status/stream`,
      ),
    )

    const handleProgress = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as ConversationAttachmentStatus
      onProgress(payload)
    }

    source.addEventListener("progress", handleProgress)
    source.addEventListener("done", (event) => {
      const payload = JSON.parse((event as MessageEvent<string>).data) as ConversationAttachmentStatus
      onDone?.(payload)
      source.close()
    })
    source.addEventListener("error", (event) => {
      if (source.readyState === EventSource.CLOSED) {
        return
      }
      onError?.("附件进度订阅中断")
      if ("data" in event && typeof event.data === "string" && event.data) {
        try {
          onError?.(JSON.parse(event.data).error || "附件进度订阅中断")
        } catch {
          onError?.("附件进度订阅中断")
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
