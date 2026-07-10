import type { components } from "./generated-api"

type Schemas = components["schemas"]

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
  chunk_id?: string
  chunk_index?: number
  evidence_id?: string
  document_id?: string
  file_id?: string
  conversation_id?: string
  score?: number
  source?: string
  retrieval_type?: string
  document_title?: string
  file_type?: string
  status?: string
  page?: number | null
  page_start?: number | null
  page_end?: number | null
  content_type?: string
  artifact?: EvidenceArtifact | null
  artifact_quality?: EvidenceArtifactQuality | null
  source_locator?: SourceLocatorSummary | null
  quality_notes?: string[]
  section_path?: string[]
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
  evidence?: EvidenceItem[]
  evidence_quality?: EvidenceQuality | null
  citation_warnings?: string[]
  citation_quality?: CitationQuality | null
  recommended_resources?: RecommendedResource[]
}

export type MessagePayload = Omit<
  Schemas["MessageAdd"],
  "role" | "sources" | "evidence" | "evidence_quality" | "citation_warnings" | "citation_quality" | "recommended_resources"
> & {
  role: "user" | "assistant"
  sources?: SourceInfo[] | null
  evidence?: EvidenceItem[] | null
  evidence_quality?: EvidenceQuality | null
  citation_warnings?: string[] | null
  citation_quality?: CitationQuality | null
  recommended_resources?: RecommendedResource[] | null
}

export type ChatRequestPayload = Omit<Schemas["ChatRequest"], "enable_rag" | "mode"> &
  Partial<Pick<Schemas["ChatRequest"], "enable_rag" | "mode">>
export type ConversationAttachmentStatus = Schemas["ConversationAttachmentStatus"]

export interface ConversationDetail {
  id: string
  user_id?: string | null
  title: string
  assistant_id?: string | null
  messages: ConversationMessage[]
  created_at?: string | null
  updated_at?: string | null
}

export type ConversationUpdate = Schemas["ConversationUpdate"]
export type MessageUpdate = Schemas["MessageUpdate"]

export type KnowledgeSpace = Schemas["KnowledgeSpaceResponse"]
export type KnowledgeSpacesResponse = Schemas["KnowledgeSpaceListResponse"]

export type DocumentItem = Omit<Schemas["DocumentInfo"], "parse_quality"> & {
  parse_quality?: ParseQualitySummary | null
}

export type DocumentListResponse = Omit<Schemas["DocumentListResponse"], "documents"> & {
  documents: DocumentItem[]
}

export type DocumentProgress = Schemas["DocumentProgressResponse"]
export type DocumentUpdate = Schemas["DocumentUpdateRequest"]
export type TaskDispatchInfo = Schemas["TaskDispatchInfo"]
export type DocumentUploadResponse = Schemas["DocumentUploadResponse"]
export type ConversationAttachmentUploadResponse = Schemas["ConversationAttachmentUploadResponse"]
export type DocumentActionResponse = Schemas["DocumentActionResponse"]
export type ConversationCreateResponse = Schemas["ConversationCreateResponse"]
export type ConversationUpdateResponse = Schemas["ConversationUpdateResponse"]
export type ActionResponse = Schemas["ActionResponse"]
export type MessageActionResponse = Schemas["MessageActionResponse"]
export type RegenerateMessageResponse = Schemas["RegenerateMessageResponse"]

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
  source_locator?: SourceLocatorSummary | null
  quality_notes?: string[]
  chunker_type?: string | null
  parse_summary?: ParseQualitySummary | Record<string, unknown>
}

export interface DocumentChunkFacets {
  content_type_counts?: Record<string, number>
  feature_counts?: Record<string, number>
  quality_note_count?: number
  problem_chunk_count?: number
}

export type DocumentChunksResponse = Omit<
  Schemas["DocumentChunksResponse"],
  "chunks" | "parse_quality" | "facets"
> & {
  chunks: DocumentChunkPreview[]
  parse_quality?: ParseQualitySummary | null
  facets?: DocumentChunkFacets | null
}

export interface ChunkPreviewArtifact {
  type: "table" | "image_ocr" | "ocr" | "formula" | "code" | string
  markdown?: string
  headers?: string[]
  rows?: string[][]
  row_count?: number | null
  column_count?: number | null
  sources?: TableSourceRef[]
  text?: string
  image_count?: number | null
  images?: OcrImageRef[]
}

export type EvidenceArtifact = ChunkPreviewArtifact

export interface TableSourceRef {
  table_index?: number | null
  page?: number | null
  page_end?: number | null
  type?: string | null
  caption?: string | null
  title?: string | null
  source?: string | null
  target?: string | null
  row_count?: number | null
  column_count?: number | null
  bbox?: unknown
}

export interface OcrImageRef {
  page?: number | null
  image_index?: number | null
  confidence?: number | null
  line_count?: number | null
  text_length?: number | null
  text_preview?: string | null
  low_confidence?: boolean | null
  width?: number | null
  height?: number | null
  target?: string | null
  bbox?: unknown
}

export interface SourceLocatorAnchor {
  type?: string
  page?: number | null
  page_start?: number | null
  page_end?: number | null
  char_start?: number | null
  char_end?: number | null
  table_index?: number | null
  image_index?: number | null
  bbox?: unknown
  width?: number | null
  height?: number | null
  confidence?: number | null
  low_confidence?: boolean | null
  text_preview?: string | null
  source?: string | null
  target?: string | null
  caption?: string | null
  title?: string | null
  row_count?: number | null
  column_count?: number | null
  [key: string]: unknown
}

export interface SourceLocatorSummary {
  source_type?: string
  document_id?: string
  chunk_index?: number | null
  page_start?: number | null
  page_end?: number | null
  char_start?: number | null
  char_end?: number | null
  section_path?: string[]
  anchor_count?: number
  anchors?: SourceLocatorAnchor[]
  has_page?: boolean
  has_char_range?: boolean
  has_bbox?: boolean
  has_table_source?: boolean
  has_image_source?: boolean
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

export interface EvidenceItem {
  id: string
  text: string
  document_id?: string
  file_id?: string
  conversation_id?: string
  chunk_id?: string
  chunk_index?: number
  document_title?: string
  section_path?: string[]
  page?: number | null
  page_start?: number | null
  page_end?: number | null
  score?: number
  retrieval_type?: string
  metadata?: {
    content_type?: string
    page_start?: number | null
    page_end?: number | null
    preview?: string
    artifact?: EvidenceArtifact | null
    artifact_quality?: EvidenceArtifactQuality | null
    source_locator?: SourceLocatorSummary | null
    quality_notes?: string[]
    [key: string]: unknown
  }
}

export interface CitationEvidenceRef {
  id: string
  score?: number
  document_id?: string
  file_id?: string
  conversation_id?: string
  chunk_id?: string
  chunk_index?: number
  document_title?: string
  section_path?: string[]
  page?: number | null
  page_start?: number | null
  page_end?: number | null
  content_type?: string
  retrieval_type?: string
  preview?: string
  source_locator?: SourceLocatorSummary | null
  artifact_quality?: EvidenceArtifactQuality | null
  quality_notes?: string[]
  risk_reasons?: string[]
}

export interface CitationEvidenceAudit {
  id: string
  content_type?: string
  document_id?: string
  chunk_id?: string
  chunk_index?: number
  page?: number | null
  page_start?: number | null
  page_end?: number | null
  score?: number
  retrieval_type?: string
  has_source_locator?: boolean
  source_anchor_count?: number
  has_table_source?: boolean
  has_image_source?: boolean
  has_bbox?: boolean
  artifact_quality_status?: string | null
  risk_reasons?: string[]
  quality_notes?: string[]
}

export interface CitationQuality {
  status: "no_evidence" | "missing" | "invalid" | "partial" | "complete" | string
  risk_level?: "low" | "medium" | "high" | string
  evidence_count: number
  used_citation_ids: string[]
  valid_citation_ids: string[]
  invalid_citation_ids: string[]
  duplicate_citation_ids: string[]
  cited_structured_evidence_count?: number
  cited_missing_source_locator_ids?: string[]
  cited_artifact_warning_ids?: string[]
  cited_low_confidence_ocr_ids?: string[]
  cited_quality_note_ids?: string[]
  evidence_citation_audit?: CitationEvidenceAudit[]
  cited_risky_evidence?: CitationEvidenceRef[]
  unused_evidence_ids: string[]
  unreferenced_top_evidence_ids: string[]
  unreferenced_top_evidence?: CitationEvidenceRef[]
  coverage?: number | null
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

export type RuntimeConfigResponse = Schemas["RuntimeConfigResponse"]
export type RuntimeConfigUpdate = Schemas["RuntimeConfigUpdateRequest"]
export type AgentConfigItem = Schemas["AgentConfigItemResponse"]
export type AgentConfigsResponse = Schemas["AgentConfigsListResponse"]
export type AgentConfigUpdate = Schemas["AgentConfigUpdateRequest"]

export type DeepResearchEvaluateRequest = Schemas["DeepResearchEvaluateRequest"]
export type DeepResearchEvaluation = Schemas["DeepResearchGateDecision"]
export type DeepResearchRequest = Schemas["DeepResearchRequest"]

export interface DeepResearchAgentResult {
  agent_type: string
  content: string
  title?: string
  sources?: SourceInfo[]
  evidence?: EvidenceItem[]
  evidence_ids?: string[]
  claims?: string[]
  open_questions?: string[]
  confidence?: number
}

export interface DeepResearchAgentStatus {
  agent_type: string
  status: "pending" | "running" | "completed" | "error" | "skipped" | string
  current_step?: string
  progress?: number
  details?: string
  dependencies?: string[]
  started_at?: number | string
  completed_at?: number | string
}

export interface DeepResearchStreamEvent {
  type?: "planning" | "agent_result" | "agent_status" | "html" | "markdown" | "text" | string
  done?: boolean
  error?: string
  run_id?: string
  content?: string
  title?: string
  selected_agents?: string[]
  agent_tasks?: Record<string, string>
  dependencies?: unknown
  parallel_groups?: unknown[]
  reasoning?: string
  agent_type?: string
  sources?: SourceInfo[]
  evidence?: EvidenceItem[]
  evidence_ids?: string[]
  claims?: string[]
  open_questions?: string[]
  confidence?: number
  status?: DeepResearchAgentStatus["status"]
  current_step?: string
  progress?: number
  details?: string
  started_at?: number | string
  completed_at?: number | string
  artifact?: unknown
}

export interface ChatStreamEvent {
  content?: string
  done?: boolean
  error?: string
  sources?: SourceInfo[]
  evidence?: EvidenceItem[]
  evidence_quality?: EvidenceQuality | null
  citation_warnings?: string[]
  citation_quality?: CitationQuality | null
  recommended_resources?: RecommendedResource[]
}
