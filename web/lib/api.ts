/**
 * 浏览器端 API 客户端：请求经 Next rewrites 转发到 FastAPI（/api/* → 后端）。
 */

import type { EvidenceItem, SourceInfo } from "@/types/chat";

export type ApiResult<T> = { data?: T; error?: string };

export type RuntimeMode = "low" | "high" | "custom";

export type RuntimeConfigResponse = {
  mode: RuntimeMode;
  modules: Record<string, boolean>;
  params: Record<string, unknown>;
  updated_at?: string | null;
};

export type AgentConfigItem = {
  agent_type: string;
  label: string;
  role: string;
  inference_model?: string | null;
  embedding_model?: string | null;
  system_prompt?: string | null;
  builtin_system_prompt: string;
  enabled: boolean;
  enable_locked?: boolean;
};

export type KnowledgeSpace = {
  id: string;
  name: string;
  description?: string | null;
  collection_name: string;
  is_default: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type Document = {
  id: string;
  title: string;
  file_type: string;
  file_size: number;
  created_at: string;
  status: string;
  progress_percentage?: number | null;
  current_stage?: string | null;
  stage_details?: string | null;
  parse_quality?: ParseQualitySummary | null;
};

export type Model = {
  name: string;
  size?: number;
  modified_at?: string;
  digest?: string;
  /** Ollama /api/tags 返回的嵌套字段 */
  details?: { parameter_size?: string | number; family?: string };
};

export type DocumentDetail = {
  id: string;
  title: string;
  file_type: string;
  file_size: number;
  created_at: string;
  updated_at: string;
  status: string;
  progress_percentage?: number | null;
  current_stage?: string | null;
  stage_details?: string | null;
  file_path: string;
  metadata?: Record<string, unknown> | null;
  processing_stages: Array<Record<string, unknown>>;
  chunks: Array<Record<string, unknown>>;
  vectors: Array<Record<string, unknown>>;
  total_chunks: number;
  total_vectors: number;
};

export type DocumentChunkPreview = {
  id: string;
  document_id?: string;
  chunk_index?: number;
  text?: string;
  preview: string;
  content_type: string;
  section_path: string[];
  page?: number | null;
  page_start?: number | null;
  page_end?: number | null;
  char_start?: number | null;
  char_end?: number | null;
  token_count?: number | null;
  features?: Record<string, boolean>;
  artifact?: ChunkPreviewArtifact | null;
  chunker_type?: string | null;
  parse_summary?: ParseQualitySummary | Record<string, unknown>;
};

export type ChunkPreviewArtifact = {
  type: "table" | "image_ocr" | "ocr" | "formula" | "code" | string;
  markdown?: string;
  headers?: string[];
  rows?: string[][];
  row_count?: number | null;
  column_count?: number | null;
  text?: string;
  image_count?: number | null;
  images?: OcrImageRef[];
};

export type OcrImageRef = {
  page?: number | null;
  image_index?: number | null;
  confidence?: number | null;
  line_count?: number | null;
  text_length?: number | null;
  width?: number | null;
  height?: number | null;
};

export type DocumentChunksResponse = {
  document_id: string;
  title: string;
  status: string;
  chunks: DocumentChunkPreview[];
  total_chunks: number;
  total_all_chunks?: number | null;
  skip: number;
  limit: number;
  parse_quality?: ParseQualitySummary | null;
  filters?: {
    content_type?: string | null;
    feature?: string | null;
    q?: string | null;
  };
};

export type ParseQualitySummary = {
  parser_type?: string | null;
  extraction_method?: string | null;
  page_count?: number | null;
  extracted_pages?: number | null;
  table_count?: number;
  formula_count?: number;
  image_count?: number;
  ocr_text_length?: number;
  text_length?: number;
  chunk_count?: number;
  content_type_counts?: Record<string, number>;
  page_coverage?: number | null;
  quality_score?: number;
  risk_level?: "low" | "medium" | "high" | string;
  quality_checks?: ParseQualityCheck[];
  recommendations?: string[];
  warnings?: string[];
};

export type ParseQualityCheck = {
  id: string;
  label: string;
  status: "pass" | "warn" | "fail" | string;
  severity: "info" | "warning" | "critical" | string;
  message: string;
  action?: string;
};

export type ConversationMessage = {
  message_id?: string;
  role: string;
  content: string;
  timestamp?: string | null;
  sources?: unknown[];
  recommended_resources?: unknown[];
};

export type ConversationDetail = {
  id: string;
  title: string;
  assistant_id?: string | null;
  messages: ConversationMessage[];
  created_at?: string | null;
  updated_at?: string | null;
};

function parseHttpError(payload: unknown): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const d = (payload as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d
        .map((x) =>
          typeof x === "object" && x !== null && "msg" in x
            ? String((x as { msg: string }).msg)
            : String(x),
        )
        .join("; ");
    }
  }
  return "请求失败";
}

async function readJson<T>(res: Response): Promise<T | undefined> {
  const text = await res.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as T;
  } catch {
    return undefined;
  }
}

async function requestJson<T>(
  input: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(input, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.headers as Record<string, string>),
      },
    });
    const payload = await readJson<unknown>(res);
    if (!res.ok) {
      return { error: parseHttpError(payload) };
    }
    return { data: payload as T };
  } catch (e) {
    return { error: (e as Error).message || "网络错误" };
  }
}

export type ChatClientParams = {
  message: string;
  assistant_id?: string;
  knowledge_space_ids?: string[];
  conversation_id?: string | null;
  enable_rag?: boolean;
  mode?: string;
  generation_config?: Record<string, unknown>;
};

export type DeepResearchClientParams = {
  message: string;
  assistant_id?: string;
  conversation_id?: string | null;
  enabled_agents?: string[];
  generation_config?: Record<string, unknown>;
};

export type RetrievalBody = {
  query: string;
  document_id?: string | null;
  top_k?: number;
  assistant_id?: string | null;
  knowledge_space_ids?: string[];
  conversation_id?: string | null;
};

const apiClientImpl = {
  async getRuntimeSettings(): Promise<ApiResult<RuntimeConfigResponse>> {
    return requestJson<RuntimeConfigResponse>("/api/settings/runtime");
  },

  async updateRuntimeSettings(
    body: Partial<{
      mode: RuntimeMode;
      modules: Record<string, boolean>;
      params: Record<string, unknown>;
    }>,
  ): Promise<ApiResult<RuntimeConfigResponse>> {
    return requestJson<RuntimeConfigResponse>("/api/settings/runtime", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  async listAgentConfigs(): Promise<ApiResult<{ agents: AgentConfigItem[] }>> {
    return requestJson<{ agents: AgentConfigItem[] }>("/api/settings/agents");
  },

  async updateAgentConfig(
    agentType: string,
    body: {
      inference_model?: string | null;
      embedding_model?: string | null;
      system_prompt?: string | null;
      enabled?: boolean;
      clear_system_prompt?: boolean;
    },
  ): Promise<ApiResult<AgentConfigItem>> {
    return requestJson<AgentConfigItem>(`/api/settings/agents/${encodeURIComponent(agentType)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  async listModels(): Promise<ApiResult<{ models: Model[] }>> {
    return requestJson<{ models: Model[] }>("/api/chat/models");
  },

  async listKnowledgeSpaces(): Promise<
    ApiResult<{ knowledge_spaces: KnowledgeSpace[]; total: number }>
  > {
    return requestJson<{ knowledge_spaces: KnowledgeSpace[]; total: number }>(
      "/api/knowledge-spaces",
    );
  },

  async createKnowledgeSpace(body: {
    name: string;
    description?: string;
  }): Promise<ApiResult<KnowledgeSpace>> {
    return requestJson<KnowledgeSpace>("/api/knowledge-spaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  async listDocuments(
    knowledgeSpaceId?: string,
    skip = 0,
    limit = 100,
  ): Promise<ApiResult<{ documents: Document[]; total: number }>> {
    const q = new URLSearchParams();
    q.set("skip", String(skip));
    q.set("limit", String(limit));
    if (knowledgeSpaceId) q.set("knowledge_space_id", knowledgeSpaceId);
    return requestJson<{ documents: Document[]; total: number }>(
      `/api/documents?${q.toString()}`,
    );
  },

  async getDocumentDetail(docId: string): Promise<ApiResult<DocumentDetail>> {
    return requestJson<DocumentDetail>(`/api/documents/${encodeURIComponent(docId)}`);
  },

  async getDocumentChunks(
    docId: string,
    options?: { skip?: number; limit?: number; includeText?: boolean; contentType?: string; feature?: string; query?: string },
  ): Promise<ApiResult<DocumentChunksResponse>> {
    const q = new URLSearchParams();
    q.set("skip", String(options?.skip ?? 0));
    q.set("limit", String(options?.limit ?? 100));
    q.set("include_text", String(options?.includeText ?? true));
    if (options?.contentType && options.contentType !== "all") q.set("content_type", options.contentType);
    if (options?.feature && options.feature !== "all") q.set("feature", options.feature);
    if (options?.query?.trim()) q.set("q", options.query.trim());
    return requestJson<DocumentChunksResponse>(
      `/api/documents/${encodeURIComponent(docId)}/chunks?${q.toString()}`,
    );
  },

  async deleteDocument(docId: string): Promise<ApiResult<{ success?: boolean }>> {
    return requestJson<{ success?: boolean }>(`/api/documents/${encodeURIComponent(docId)}`, {
      method: "DELETE",
    });
  },

  async createConversation(title: string): Promise<
    ApiResult<{ id: string; title: string; created_at: string; updated_at: string }>
  > {
    return requestJson<{ id: string; title: string; created_at: string; updated_at: string }>(
      "/api/chat/conversations",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      },
    );
  },

  async getConversation(conversationId: string): Promise<ApiResult<ConversationDetail>> {
    return requestJson<ConversationDetail>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}`,
    );
  },

  async addMessageToConversation(
    conversationId: string,
    role: string,
    content: string,
    sources?: unknown[],
    recommended_resources?: unknown[],
    evidence?: unknown[],
    citation_warnings?: string[],
  ): Promise<ApiResult<{ success?: boolean; timestamp?: string }>> {
    const body: Record<string, unknown> = { role, content };
    if (sources !== undefined) body.sources = sources;
    if (recommended_resources !== undefined) body.recommended_resources = recommended_resources;
    if (evidence !== undefined) body.evidence = evidence;
    if (citation_warnings !== undefined) body.citation_warnings = citation_warnings;
    return requestJson<{ success?: boolean; timestamp?: string }>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
  },

  async analyzeQuery(
    query: string,
  ): Promise<ApiResult<{ need_retrieval: boolean; reason: string; confidence?: string }>> {
    return requestJson<{ need_retrieval: boolean; reason: string; confidence?: string }>(
      "/api/retrieval/analyze",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      },
    );
  },

  async retrieve(body: RetrievalBody): Promise<
    ApiResult<{
      context: string;
      sources: SourceInfo[];
      evidence?: EvidenceItem[];
      citation_warnings?: string[];
      retrieval_count?: number;
      recommended_resources?: Record<string, unknown>[];
    }>
  > {
    return requestJson<{
      context: string;
      sources: SourceInfo[];
      evidence?: EvidenceItem[];
      citation_warnings?: string[];
      retrieval_count?: number;
      recommended_resources?: Record<string, unknown>[];
    }>("/api/retrieval", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  async evaluateDeepResearch(body: {
    message: string;
    conversation_id?: string | null;
  }): Promise<
    ApiResult<{ should_deep_research: boolean; score: number; threshold: number; reasons: string[] }>
  > {
    return requestJson<{
      should_deep_research: boolean;
      score: number;
      threshold: number;
      reasons: string[];
    }>("/api/chat/deep-research/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: body.message,
        conversation_id: body.conversation_id ?? undefined,
      }),
    });
  },

  async chat(
    params: ChatClientParams,
    signal?: AbortSignal,
  ): Promise<ReadableStream<Uint8Array> | null> {
    try {
      const res = await fetch("/api/chat/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          query: params.message,
          assistant_id: params.assistant_id,
          knowledge_space_ids: params.knowledge_space_ids,
          conversation_id: params.conversation_id ?? undefined,
          enable_rag: params.enable_rag ?? true,
          mode: params.mode ?? "normal",
          generation_config: params.generation_config,
        }),
        signal,
      });
      if (!res.ok) return null;
      return res.body;
    } catch {
      return null;
    }
  },

  async deepResearchChat(
    params: DeepResearchClientParams,
    signal?: AbortSignal,
  ): Promise<ReadableStream<Uint8Array> | null> {
    try {
      const res = await fetch("/api/chat/deep-research", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          query: params.message,
          assistant_id: params.assistant_id,
          conversation_id: params.conversation_id ?? undefined,
          enabled_agents: params.enabled_agents,
          generation_config: params.generation_config,
        }),
        signal,
      });
      if (!res.ok) return null;
      return res.body;
    } catch {
      return null;
    }
  },

  async updateMessage(
    conversationId: string,
    messageId: string,
    content: string,
  ): Promise<ApiResult<{ success?: boolean; message_id?: string; timestamp?: string }>> {
    return requestJson<{ success?: boolean; message_id?: string; timestamp?: string }>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      },
    );
  },

  async regenerateResponse(
    conversationId: string,
    messageId: string,
  ): Promise<ApiResult<{ success?: boolean; remaining_messages?: number }>> {
    return requestJson<{ success?: boolean; remaining_messages?: number }>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/regenerate`,
      { method: "POST" },
    );
  },

  async uploadConversationAttachment(
    conversationId: string,
    knowledgeSpaceId: string,
    file: File,
  ): Promise<
    ApiResult<{ file_id: string; document_id?: string; status: string; message?: string }>
  > {
    const form = new FormData();
    form.append("file", file);
    form.append("conversation_id", conversationId);
    form.append("knowledge_space_id", knowledgeSpaceId);
    try {
      const res = await fetch("/api/chat/conversation-attachment", {
        method: "POST",
        body: form,
      });
      const payload = await readJson<unknown>(res);
      if (!res.ok) {
        return { error: parseHttpError(payload) };
      }
      return { data: payload as { file_id: string; document_id?: string; status: string; message?: string } };
    } catch (e) {
      return { error: (e as Error).message || "上传失败" };
    }
  },

  async getConversationAttachmentStatus(
    conversationId: string,
    fileId: string,
  ): Promise<
    ApiResult<{
      file_id: string;
      conversation_id: string;
      filename: string;
      status: string;
      progress_percentage?: number;
      current_stage?: string | null;
      stage_details?: string | null;
      message?: string | null;
    }>
  > {
    return requestJson(
      `/api/chat/conversation-attachment/${encodeURIComponent(conversationId)}/${encodeURIComponent(fileId)}/status`,
    );
  },
};

export const apiClient = apiClientImpl;
