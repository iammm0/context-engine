/** 聊天相关类型定义 */

/** 单次对话触发的 RAG 评测指标（用于折叠面板展示） */
export interface RAGEvaluationMetrics {
  /** 是否触发了增强检索 */
  retrieval_triggered: boolean;
  /** 召回条数（来源 chunk 数） */
  source_count: number;
  /** 上下文字符长度 */
  context_length: number;
  /** 检索耗时（毫秒） */
  retrieval_time_ms?: number;
  /** 首 token 前耗时（毫秒） */
  time_to_first_token_ms?: number;
  /** 总响应耗时（毫秒） */
  response_time_ms?: number;
  /** 异常标记：如 响应时间>500ms、召回率低 等，用于告警展示 */
  warnings?: string[];
}

export interface ChatMessage {
  message_id?: string; // 消息唯一ID
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  sources?: SourceInfo[]; // 文档来源（普通模式）
  evidence?: EvidenceItem[]; // chunk级证据（普通模式）
  citation_warnings?: string[]; // 引用校验提醒
  recommended_resources?: RecommendedResource[]; // 推荐的相关资源（普通模式）
  recommended_users?: RecommendedUser[]; // 推荐用户（网络模式）
  user_relationships?: UserRelationship[]; // 用户关系（网络模式）
  recommendation_reason?: string; // 推荐理由（网络模式）
  cypher_queries?: CypherQuery[]; // Cypher查询思维链（网络模式）
  /** 本条回复的 RAG 评测指标（仅助手消息，折叠展示） */
  rag_metrics?: RAGEvaluationMetrics;
}

export interface CypherQuery {
  step: string; // 步骤名称
  description: string; // 步骤描述
  query: string; // Cypher查询语句
  result_count?: number; // 查询结果数量
}

export interface RecommendedUser {
  user_id: string;
  username: string;
  user_type: string;
  score?: number;
  reason?: string;
  properties?: {
    full_name?: string;
    avatar_url?: string;
    research_fields?: string[];
    college?: string;
    major?: string;
    skills?: string[];
  };
}

export interface UserRelationship {
  from_user_id: string;
  from_username?: string;
  to_user_id: string;
  to_username?: string;
  relationship_type: string;
  properties?: Record<string, unknown>;
}

export interface RecommendedResource {
  resource_id: string;
  title: string;
  description: string;
  file_type: string;
  file_size: number;
  score: number;
}

export interface SourceInfo {
  chunk_id?: string;
  chunk_index?: number;
  evidence_id?: string;
  document_id?: string;
  file_id?: string;
  conversation_id?: string;
  score: number;
  retrieval_type: string;
  document_title?: string; // 文档标题
  file_type?: string; // 文件类型
  status?: string; // 文档状态
  page?: number | null;
  page_start?: number | null;
  page_end?: number | null;
  content_type?: string;
  artifact?: EvidenceArtifact | null;
  section_path?: string[];
}

export interface EvidenceArtifact {
  type: "table" | "image_ocr" | "ocr" | "formula" | "code" | string;
  markdown?: string;
  headers?: string[];
  rows?: string[][];
  row_count?: number | null;
  column_count?: number | null;
  sources?: TableSourceRef[];
  text?: string;
  image_count?: number | null;
  images?: OcrImageRef[];
}

export interface TableSourceRef {
  table_index?: number | null;
  page?: number | null;
  page_end?: number | null;
  type?: string | null;
  caption?: string | null;
  title?: string | null;
  source?: string | null;
  target?: string | null;
  row_count?: number | null;
  column_count?: number | null;
  bbox?: unknown;
}

export interface OcrImageRef {
  page?: number | null;
  image_index?: number | null;
  confidence?: number | null;
  line_count?: number | null;
  text_length?: number | null;
  width?: number | null;
  height?: number | null;
  target?: string | null;
}

export interface EvidenceItem {
  id: string;
  text: string;
  document_id?: string;
  file_id?: string;
  conversation_id?: string;
  chunk_id?: string;
  chunk_index?: number;
  document_title?: string;
  section_path?: string[];
  page?: number;
  score: number;
  retrieval_type: string;
  metadata?: {
    content_type?: string;
    page_start?: number | null;
    page_end?: number | null;
    preview?: string;
    artifact?: EvidenceArtifact | null;
    [key: string]: unknown;
  };
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
  document_id?: string;
}

export interface ChatResponse {
  response: string;
  conversation_id: string;
  sources?: SourceInfo[];
  evidence?: EvidenceItem[];
  citation_warnings?: string[];
}
