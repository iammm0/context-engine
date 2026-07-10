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

export type KnowledgeSpace = Schemas["KnowledgeSpaceResponse"]
export type KnowledgeSpacesResponse = Schemas["KnowledgeSpaceListResponse"]

export type DocumentItem = Omit<Schemas["DocumentInfo"], "parse_quality"> & {
  parse_quality?: ParseQualitySummary | null
}

export type DocumentListResponse = Omit<Schemas["DocumentListResponse"], "documents"> & {
  documents: DocumentItem[]
}

export type DocumentProgress = Schemas["DocumentProgressResponse"]

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
export type AgentConfigItem = Schemas["AgentConfigItemResponse"]
export type AgentConfigsResponse = Schemas["AgentConfigsListResponse"]

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
