import type {
  AgentConfigUpdate,
  ApiEnvelope,
  ChatRequestPayload,
  ChatStreamEvent,
  ConversationAttachmentStatus,
  DocumentChunksResponse,
  DeepResearchEvaluateRequest,
  DeepResearchRequest,
  DeepResearchStreamEvent,
  ConversationUpdate,
  ConversationDetail,
  DocumentListResponse,
  DocumentProgress,
  DocumentUpdate,
  MessageUpdate,
  MessagePayload,
  RuntimeConfigUpdate,
  TaskDispatchInfo,
} from "@/types/api"
import type { paths } from "@/types/generated-api"

type ProgressSubscriber = (progress: DocumentProgress) => void
type AttachmentProgressSubscriber = (progress: ConversationAttachmentStatus) => void
type TaskProgressSubscriber = (progress: TaskDispatchInfo) => void
type JsonMethod = "get" | "post" | "put" | "delete"
type SuccessStatus = 200 | 201 | 202 | 204

type OperationFor<Path extends keyof paths, Method extends JsonMethod> = paths[Path][Method]
type JsonResponseContent<Response> = Response extends { content: { "application/json": infer Body } } ? Body : never
type JsonResponseFor<Path extends keyof paths, Method extends JsonMethod> =
  OperationFor<Path, Method> extends { responses: infer Responses }
    ? JsonResponseContent<Responses[Extract<keyof Responses, SuccessStatus>]>
    : never
type JsonRequestBodyFor<Path extends keyof paths, Method extends JsonMethod> =
  OperationFor<Path, Method> extends { requestBody: { content: { "application/json": infer Body } } } ? Body : never
type JsonRequestOptions = Omit<RequestInit, "method" | "body">

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

type EventStreamOptions<T> = {
  fallbackError: string
  onDone?: (payload: T) => void
  onError?: (message: string) => void
  onProgress: (payload: T) => void
  path: string
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

async function requestJson<T>(path: string, init?: RequestInit, fallbackError = "网络错误"): Promise<ApiEnvelope<T>> {
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
    return { error: error instanceof Error ? error.message : fallbackError }
  }
}

function jsonHeaders(headers?: HeadersInit): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(headers as Record<string, string> | undefined),
  }
}

function getJson<Path extends keyof paths, Result = JsonResponseFor<Path, "get">>(
  _route: Path,
  path: string = _route,
  init?: JsonRequestOptions,
) {
  return requestJson<Result>(path, { ...init, method: "GET" })
}

function deleteJson<Path extends keyof paths, Result = JsonResponseFor<Path, "delete">>(
  _route: Path,
  path: string = _route,
  init?: JsonRequestOptions,
) {
  return requestJson<Result>(path, { ...init, method: "DELETE" })
}

function postJson<Path extends keyof paths, Result = JsonResponseFor<Path, "post">>(
  _route: Path,
  path: string,
  body?: JsonRequestBodyFor<Path, "post">,
  init?: JsonRequestOptions,
) {
  return requestJson<Result>(path, {
    ...init,
    method: "POST",
    headers: body === undefined ? init?.headers : jsonHeaders(init?.headers),
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

function postForm<Path extends keyof paths, Result = JsonResponseFor<Path, "post">>(
  _route: Path,
  path: string,
  body: FormData,
  fallbackError: string,
  init?: JsonRequestOptions,
) {
  return requestJson<Result>(
    path,
    {
      ...init,
      method: "POST",
      body,
    },
    fallbackError,
  )
}

function putJson<Path extends keyof paths, Result = JsonResponseFor<Path, "put">>(
  _route: Path,
  path: string,
  body: JsonRequestBodyFor<Path, "put">,
  init?: JsonRequestOptions,
) {
  return requestJson<Result>(path, {
    ...init,
    method: "PUT",
    headers: jsonHeaders(init?.headers),
    body: JSON.stringify(body),
  })
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

function subscribeEventStream<T>({ fallbackError, onDone, onError, onProgress, path }: EventStreamOptions<T>) {
  const source = new EventSource(apiUrl(path))

  source.addEventListener("progress", (event) => {
    const payload = JSON.parse((event as MessageEvent<string>).data) as T
    onProgress(payload)
  })
  source.addEventListener("done", (event) => {
    const payload = JSON.parse((event as MessageEvent<string>).data) as T
    onDone?.(payload)
    source.close()
  })
  source.addEventListener("error", (event) => {
    if (source.readyState === EventSource.CLOSED) {
      return
    }
    onError?.(fallbackError)
    if ("data" in event && typeof event.data === "string" && event.data) {
      try {
        onError?.(JSON.parse(event.data).error || fallbackError)
      } catch {
        onError?.(fallbackError)
      }
    }
  })

  return () => source.close()
}

export const api = {
  getRoot() {
    return getJson<"/">("/")
  },

  getHealth() {
    return getJson<"/health">("/health")
  },

  getReadiness() {
    return getJson<"/health/readiness">("/health/readiness")
  },

  getMetrics() {
    return getJson<"/health/metrics">("/health/metrics")
  },

  getModels() {
    return getJson<"/api/chat/models">("/api/chat/models")
  },

  getConversations() {
    return getJson<"/api/chat/conversations">("/api/chat/conversations")
  },

  createConversation(title: string) {
    return postJson<"/api/chat/conversations">(
      "/api/chat/conversations",
      "/api/chat/conversations",
      { title },
    )
  },

  getConversation(conversationId: string) {
    return getJson<"/api/chat/conversations/{conversation_id}", ConversationDetail>(
      "/api/chat/conversations/{conversation_id}",
      `/api/chat/conversations/${encodeURIComponent(conversationId)}`,
    )
  },

  updateConversation(conversationId: string, body: ConversationUpdate) {
    return putJson<"/api/chat/conversations/{conversation_id}">(
      "/api/chat/conversations/{conversation_id}",
      `/api/chat/conversations/${encodeURIComponent(conversationId)}`,
      body,
    )
  },

  deleteConversation(conversationId: string) {
    return deleteJson<"/api/chat/conversations/{conversation_id}">(
      "/api/chat/conversations/{conversation_id}",
      `/api/chat/conversations/${encodeURIComponent(conversationId)}`,
    )
  },

  addConversationMessage(conversationId: string, body: MessagePayload) {
    return postJson<"/api/chat/conversations/{conversation_id}/messages">(
      "/api/chat/conversations/{conversation_id}/messages",
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages`,
      body as JsonRequestBodyFor<"/api/chat/conversations/{conversation_id}/messages", "post">,
    )
  },

  updateConversationMessage(conversationId: string, messageId: string, body: MessageUpdate) {
    return putJson<"/api/chat/conversations/{conversation_id}/messages/{message_id}">(
      "/api/chat/conversations/{conversation_id}/messages/{message_id}",
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}`,
      body,
    )
  },

  regenerateConversationMessage(conversationId: string, messageId: string) {
    return postJson<"/api/chat/conversations/{conversation_id}/messages/{message_id}/regenerate">(
      "/api/chat/conversations/{conversation_id}/messages/{message_id}/regenerate",
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/regenerate`,
    )
  },

  async streamChat(body: ChatRequestPayload, onEvent: (event: ChatStreamEvent) => void, signal?: AbortSignal) {
    const response = await fetch(apiUrl("/api/chat/"), {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      signal,
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      const payload = await readJson<unknown>(response)
      throw new Error(parseHttpError(payload))
    }

    await parseSseResponse<ChatStreamEvent>(response, onEvent)
  },

  evaluateDeepResearch(body: DeepResearchEvaluateRequest) {
    return postJson<"/api/chat/deep-research/evaluate">(
      "/api/chat/deep-research/evaluate",
      "/api/chat/deep-research/evaluate",
      body,
    )
  },

  queueQueryAnalysis(query: string) {
    return postJson<"/api/retrieval/analyze/task">(
      "/api/retrieval/analyze/task",
      "/api/retrieval/analyze/task",
      { query },
    )
  },

  analyzeQuery(query: string) {
    return postJson<"/api/retrieval/analyze">(
      "/api/retrieval/analyze",
      "/api/retrieval/analyze",
      { query },
    )
  },

  async streamDeepResearch(body: DeepResearchRequest, onEvent: (event: DeepResearchStreamEvent) => void, signal?: AbortSignal) {
    const response = await fetch(apiUrl("/api/chat/deep-research"), {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      signal,
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      const payload = await readJson<unknown>(response)
      throw new Error(parseHttpError(payload))
    }

    await parseSseResponse<DeepResearchStreamEvent>(response, onEvent)
  },

  queueDeepResearch(body: DeepResearchRequest) {
    return postJson<"/api/chat/deep-research/task">(
      "/api/chat/deep-research/task",
      "/api/chat/deep-research/task",
      body,
    )
  },

  getKnowledgeSpaces() {
    return getJson<"/api/knowledge-spaces">("/api/knowledge-spaces")
  },

  createKnowledgeSpace(name: string, description?: string) {
    return postJson<"/api/knowledge-spaces">(
      "/api/knowledge-spaces",
      "/api/knowledge-spaces",
      { name, description },
    )
  },

  getDocuments(knowledgeSpaceId?: string) {
    return getJson<"/api/documents", DocumentListResponse>(
      "/api/documents",
      `/api/documents${buildQuery({ skip: 0, limit: 100, knowledge_space_id: knowledgeSpaceId })}`,
    )
  },

  getDocumentChunks(documentId: string, options?: DocumentChunksOptions) {
    return getJson<"/api/documents/{doc_id}/chunks", DocumentChunksResponse>(
      "/api/documents/{doc_id}/chunks",
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
    return putJson<"/api/documents/{doc_id}">(
      "/api/documents/{doc_id}",
      `/api/documents/${encodeURIComponent(documentId)}`,
      body,
    )
  },

  deleteDocument(documentId: string) {
    return deleteJson<"/api/documents/{doc_id}">(
      "/api/documents/{doc_id}",
      `/api/documents/${encodeURIComponent(documentId)}`,
    )
  },

  retryDocumentProcessing(documentId: string) {
    return postJson<"/api/documents/{doc_id}/retry">(
      "/api/documents/{doc_id}/retry",
      `/api/documents/${encodeURIComponent(documentId)}/retry`,
    )
  },

  documentPreviewUrl(documentId: string, page?: number | null) {
    const pageFragment = typeof page === "number" && page > 0 ? `#page=${page}` : ""
    return `${apiUrl(`/api/documents/${encodeURIComponent(documentId)}/preview`)}${pageFragment}`
  },

  uploadDocument(knowledgeSpaceId: string, file: File) {
    const form = new FormData()
    form.append("file", file)
    form.append("knowledge_space_id", knowledgeSpaceId)

    return postForm<"/api/documents/upload">(
      "/api/documents/upload",
      "/api/documents/upload",
      form,
      "上传失败",
    )
  },

  subscribeDocumentProgress(
    documentId: string,
    onProgress: ProgressSubscriber,
    onDone?: ProgressSubscriber,
    onError?: (message: string) => void,
  ) {
    return subscribeEventStream<DocumentProgress>({
      fallbackError: "文档进度订阅中断",
      onDone,
      onError,
      onProgress,
      path: `/api/documents/${encodeURIComponent(documentId)}/progress/stream`,
    })
  },

  uploadConversationAttachment(
    conversationId: string,
    knowledgeSpaceId: string,
    file: File,
  ) {
    const form = new FormData()
    form.append("file", file)
    form.append("conversation_id", conversationId)
    form.append("knowledge_space_id", knowledgeSpaceId)

    return postForm<"/api/chat/conversation-attachment">(
      "/api/chat/conversation-attachment",
      "/api/chat/conversation-attachment",
      form,
      "附件上传失败",
    )
  },

  getConversationAttachmentStatus(conversationId: string, fileId: string) {
    return getJson<"/api/chat/conversation-attachment/{conversation_id}/{file_id}/status">(
      "/api/chat/conversation-attachment/{conversation_id}/{file_id}/status",
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
    return subscribeEventStream<ConversationAttachmentStatus>({
      fallbackError: "附件进度订阅中断",
      onDone,
      onError,
      onProgress,
      path: `/api/chat/conversation-attachment/${encodeURIComponent(conversationId)}/${encodeURIComponent(fileId)}/status/stream`,
    })
  },

  getTaskStatus(taskId: string, backend = "celery") {
    const query = buildQuery({ backend })
    return getJson<"/api/tasks/{task_id}">(
      "/api/tasks/{task_id}",
      `/api/tasks/${encodeURIComponent(taskId)}${query}`,
    )
  },

  subscribeTaskStatus(
    taskId: string,
    onProgress: TaskProgressSubscriber,
    onDone?: TaskProgressSubscriber,
    onError?: (message: string) => void,
    backend = "celery",
  ) {
    const query = buildQuery({ backend })
    return subscribeEventStream<TaskDispatchInfo>({
      fallbackError: "任务状态订阅中断",
      onDone,
      onError,
      onProgress,
      path: `/api/tasks/${encodeURIComponent(taskId)}/stream${query}`,
    })
  },

  getRuntimeConfig() {
    return getJson<"/api/settings/runtime">("/api/settings/runtime")
  },

  updateRuntimeConfig(body: RuntimeConfigUpdate) {
    return putJson<"/api/settings/runtime">(
      "/api/settings/runtime",
      "/api/settings/runtime",
      body,
    )
  },

  getAgents() {
    return getJson<"/api/settings/agents">("/api/settings/agents")
  },

  updateAgentConfig(agentType: string, body: AgentConfigUpdate) {
    return putJson<"/api/settings/agents/{agent_type}">(
      "/api/settings/agents/{agent_type}",
      `/api/settings/agents/${encodeURIComponent(agentType)}`,
      body,
    )
  },
}
