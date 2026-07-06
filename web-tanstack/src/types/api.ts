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
  evidence_quality?: EvidenceQuality | null
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
  parse_quality?: ParseQualitySummary | null
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

export interface DocumentChunkPreview {
  id: string
  document_id?: string
  chunk_index?: number
  text?: string
  preview: string
  content_type: string
  section_path: string[]
  page?: number | null
  page_start?: number | null
  page_end?: number | null
  char_start?: number | null
  char_end?: number | null
  token_count?: number | null
  features?: Record<string, boolean>
  artifact?: ChunkPreviewArtifact | null
  artifact_quality?: EvidenceArtifactQuality | null
  chunker_type?: string | null
  parse_summary?: ParseQualitySummary | Record<string, unknown>
}

export interface ChunkPreviewArtifact {
  type: "table" | "image_ocr" | "ocr" | "formula" | "code" | string
  markdown?: string
  headers?: string[]
  rows?: string[][]
  row_count?: number | null
  column_count?: number | null
  text?: string
  image_count?: number | null
  images?: OcrImageRef[]
}

export interface EvidenceArtifactQuality {
  status: "not_structured" | "pass" | "warn" | string
  risk_level: "low" | "medium" | "high" | string
  structured: boolean
  content_type: string
  artifact_type: string
  has_artifact: boolean
  table_missing_structure: boolean
  table_missing_source: boolean
  ocr_missing_source: boolean
  ocr_low_confidence_source_count: number
  ocr_avg_confidence?: number | null
  warnings?: string[]
  recommendations?: string[]
}

export interface OcrImageRef {
  page?: number | null
  image_index?: number | null
  confidence?: number | null
  line_count?: number | null
  text_length?: number | null
  width?: number | null
  height?: number | null
  target?: string | null
}

export interface DocumentChunksResponse {
  document_id: string
  title: string
  status: string
  chunks: DocumentChunkPreview[]
  total_chunks: number
  total_all_chunks?: number | null
  skip: number
  limit: number
  parse_quality?: ParseQualitySummary | null
  target_chunk_id?: string | null
  target_chunk_index?: number | null
  target_found?: boolean | null
  target_offset?: number | null
  filters?: {
    content_type?: string | null
    feature?: string | null
    q?: string | null
  }
}

export interface EvidenceQuality {
  status: "no_evidence" | "pass" | "warn" | string
  risk_level: "low" | "medium" | "high" | string
  evidence_count: number
  artifact_count: number
  artifact_coverage?: number | null
  structured_evidence_count: number
  structured_artifact_count: number
  structured_artifact_coverage?: number | null
  source_locator_count?: number
  source_locator_coverage?: number | null
  structured_source_locator_count?: number
  structured_source_locator_coverage?: number | null
  missing_source_locator_count?: number
  structured_missing_source_locator_count?: number
  bbox_source_locator_count?: number
  table_source_locator_count?: number
  ocr_source_locator_count?: number
  source_anchor_count?: number
  table_count: number
  table_missing_structure_count: number
  table_missing_source_count: number
  ocr_count: number
  ocr_missing_source_count: number
  ocr_low_confidence_source_count: number
  ocr_avg_confidence?: number | null
  content_type_counts?: Record<string, number>
  artifact_type_counts?: Record<string, number>
  warnings?: string[]
  recommendations?: string[]
}

export interface ParseQualitySummary {
  parser_type?: string | null
  extraction_method?: string | null
  page_count?: number | null
  extracted_pages?: number | null
  table_count?: number
  formula_count?: number
  image_count?: number
  ocr_text_length?: number
  ocr_recognized_images?: number
  ocr_empty_images?: number
  ocr_low_confidence_images?: number
  ocr_avg_confidence?: number | null
  ocr_image_coverage?: number | null
  text_length?: number
  chunk_count?: number
  chunk_anchor_count?: number
  chunk_missing_anchor_count?: number
  chunk_anchor_coverage?: number | null
  source_locator_count?: number
  missing_source_locator_count?: number
  source_locator_coverage?: number | null
  structured_source_locator_count?: number
  structured_missing_source_locator_count?: number
  structured_source_locator_coverage?: number | null
  bbox_locator_count?: number
  table_source_locator_count?: number
  ocr_source_locator_count?: number
  chunk_token_min?: number
  chunk_token_max?: number
  chunk_token_avg?: number
  chunk_short_count?: number
  chunk_large_count?: number
  artifact_expected_count?: number
  artifact_present_count?: number
  artifact_missing_count?: number
  artifact_issue_count?: number
  artifact_preview_coverage?: number | null
  table_artifact_issue_count?: number
  table_artifact_missing_structure_count?: number
  table_artifact_missing_source_count?: number
  ocr_artifact_issue_count?: number
  ocr_artifact_missing_source_count?: number
  ocr_artifact_low_confidence_source_count?: number
  content_type_counts?: Record<string, number>
  page_coverage?: number | null
  quality_score?: number
  risk_level?: "low" | "medium" | "high" | string
  quality_checks?: ParseQualityCheck[]
  recommendations?: string[]
  warnings?: string[]
}

export interface ParseQualityCheck {
  id: string
  label: string
  status: "pass" | "warn" | "fail" | string
  severity: "info" | "warning" | "critical" | string
  message: string
  action?: string
  content_type_filter?: string | null
  feature_filter?: string | null
  filter_label?: string | null
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
  evidence_quality?: EvidenceQuality | null
  recommended_resources?: RecommendedResource[]
}
