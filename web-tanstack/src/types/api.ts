export interface ApiEnvelope<T> {
  data?: T
  error?: string
}

export interface ModelInfo {
  name: string
  size?: number
  digest?: string
  modified_at?: string
}

export interface ModelsResponse {
  models: ModelInfo[]
}

export interface ConversationSummary {
  id: string
  user_id?: string | null
  title: string
  message_count: number
  assistant_id?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ConversationListResponse {
  conversations: ConversationSummary[]
  total: number
  skip: number
  limit: number
}

export interface SourceInfo {
  title?: string
  content?: string
  document_id?: string
  chunk_id?: string
  score?: number
  source?: string
}

export interface RecommendedResource {
  title?: string
  url?: string
  description?: string
}

export interface ConversationMessage {
  message_id?: string
  role: "user" | "assistant"
  content: string
  timestamp?: string | null
  sources?: SourceInfo[]
  recommended_resources?: RecommendedResource[]
}

export interface ConversationDetail {
  id: string
  user_id?: string | null
  title: string
  assistant_id?: string | null
  messages: ConversationMessage[]
  created_at?: string | null
  updated_at?: string | null
}

export interface KnowledgeSpace {
  id: string
  name: string
  description?: string | null
  collection_name: string
  is_default: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface KnowledgeSpacesResponse {
  knowledge_spaces: KnowledgeSpace[]
  total: number
}

export interface DocumentItem {
  id: string
  title: string
  file_type: string
  file_size: number
  created_at: string
  status: string
  progress_percentage?: number
  current_stage?: string | null
  stage_details?: string | null
}

export interface DocumentListResponse {
  documents: DocumentItem[]
  total: number
}

export interface DocumentProgress {
  document_id: string
  progress_percentage: number
  current_stage: string
  stage_details: string
  status: string
}

export interface RuntimeConfigResponse {
  mode: string
  modules: Record<string, boolean>
  params: Record<string, string | number | boolean | string[] | undefined>
  updated_at?: string | null
}

export interface AgentConfigItem {
  agent_type: string
  label: string
  role: string
  inference_model?: string | null
  embedding_model?: string | null
  system_prompt?: string | null
  builtin_system_prompt: string
  enabled: boolean
  enable_locked: boolean
}

export interface AgentConfigsResponse {
  agents: AgentConfigItem[]
}

export interface DeepResearchEvaluation {
  should_deep_research: boolean
  score: number
  threshold: number
  reasons: string[]
}

export interface ChatStreamEvent {
  content?: string
  done?: boolean
  error?: string
  sources?: SourceInfo[]
  recommended_resources?: RecommendedResource[]
}
