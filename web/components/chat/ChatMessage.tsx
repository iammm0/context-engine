"use client";

import RAGEvaluationPanel from "@/components/chat/RAGEvaluationPanel";
import FormattedMessage from "@/components/message/FormattedMessage";
import ThinkingDots from "@/components/message/ThinkingDots";
import { formatChatTimestamp } from "@/lib/timezone";
import type { ChatMessage as MessageType, CitationEvidenceRef, CitationQuality, EvidenceArtifact, EvidenceItem, EvidenceQuality, OcrImageRef, SourceInfo, TableSourceRef } from "@/types/chat";
import Link from "next/link";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

const evidenceTypeLabel: Record<string, string> = {
  text: "文本",
  table: "表格",
  image_ocr: "图片OCR",
  ocr: "OCR",
  formula: "公式",
  code: "代码",
  graph: "图谱",
};

function formatSourceLocation(source: SourceInfo) {
  const pageStart = source.page_start ?? source.page ?? null;
  const pageEnd = source.page_end ?? source.page ?? null;
  const pages =
    pageStart && pageEnd && pageStart !== pageEnd
      ? `第 ${pageStart}-${pageEnd} 页`
      : pageStart
        ? `第 ${pageStart} 页`
        : "";
  const section = source.section_path?.length ? source.section_path.join(" / ") : "";
  return [pages, section].filter(Boolean).join(" · ");
}

function formatEvidenceLocation(item: EvidenceItem) {
  const pageStart = item.metadata?.page_start ?? item.page ?? null;
  const pageEnd = item.metadata?.page_end ?? item.page ?? null;
  const pages =
    pageStart && pageEnd && pageStart !== pageEnd
      ? `第 ${pageStart}-${pageEnd} 页`
      : pageStart
        ? `第 ${pageStart} 页`
        : "";
  const section = item.section_path?.length ? item.section_path.join(" / ") : "";
  const chunk = typeof item.chunk_index === "number" ? `chunk ${item.chunk_index}` : "";
  return [pages, section, chunk].filter(Boolean).join(" · ");
}

function formatCitationEvidenceLocation(item: CitationEvidenceRef) {
  const pageStart = item.page_start ?? item.page ?? null;
  const pageEnd = item.page_end ?? item.page ?? null;
  const pages =
    pageStart && pageEnd && pageStart !== pageEnd
      ? `第 ${pageStart}-${pageEnd} 页`
      : pageStart
        ? `第 ${pageStart} 页`
        : "";
  const section = item.section_path?.length ? item.section_path.join(" / ") : "";
  const chunk = typeof item.chunk_index === "number" ? `chunk ${item.chunk_index}` : "";
  return [pages, section, chunk].filter(Boolean).join(" · ");
}

function getEvidenceType(item: EvidenceItem) {
  return item.metadata?.content_type || "text";
}

function formatCitationQuality(quality?: CitationQuality | null) {
  if (!quality || typeof quality.evidence_count !== "number" || quality.evidence_count <= 0) return "";
  const bits = [];
  if (typeof quality.coverage === "number") {
    bits.push(`引用覆盖 ${Math.round(quality.coverage * 100)}%`);
  }
  if (quality.valid_citation_ids?.length) {
    bits.push(`已引用 ${quality.valid_citation_ids.join(", ")}`);
  }
  if (quality.invalid_citation_ids?.length) {
    bits.push(`无效 ${quality.invalid_citation_ids.join(", ")}`);
  }
  if (quality.duplicate_citation_ids?.length) {
    bits.push(`重复 ${quality.duplicate_citation_ids.join(", ")}`);
  }
  if (quality.unreferenced_top_evidence_ids?.length) {
    bits.push(`未引用高分证据 ${quality.unreferenced_top_evidence_ids.join(", ")}`);
  }
  return bits.join(" · ");
}

function formatEvidenceQuality(quality?: EvidenceQuality | null) {
  if (!quality || typeof quality.evidence_count !== "number" || quality.evidence_count <= 0) return "";
  const bits = [];
  if (typeof quality.structured_artifact_coverage === "number") {
    bits.push(`结构化证据 ${Math.round(quality.structured_artifact_coverage * 100)}%`);
  } else if (typeof quality.artifact_coverage === "number") {
    bits.push(`artifact ${Math.round(quality.artifact_coverage * 100)}%`);
  }
  if (quality.table_missing_structure_count > 0) {
    bits.push(`表格结构缺失 ${quality.table_missing_structure_count}`);
  }
  if (quality.table_missing_source_count > 0) {
    bits.push(`表格来源缺失 ${quality.table_missing_source_count}`);
  }
  if (quality.ocr_missing_source_count > 0) {
    bits.push(`OCR来源缺失 ${quality.ocr_missing_source_count}`);
  }
  if (quality.ocr_low_confidence_source_count > 0) {
    bits.push(`低置信OCR ${quality.ocr_low_confidence_source_count}`);
  }
  if (!bits.length && quality.status === "pass") {
    bits.push("结构化证据完整");
  }
  return bits.join(" · ");
}

function formatArtifactQualityWarnings(item: EvidenceItem) {
  const quality = item.metadata?.artifact_quality;
  if (!quality || quality.status !== "warn" || !quality.warnings?.length) return "";
  return quality.warnings.join(" · ");
}

type CitationUseState = "used" | "unused" | "unknown";

function citationUseBadge(state: CitationUseState) {
  if (state === "used") {
    return {
      label: "已引用",
      className: "bg-green-50 text-green-700 dark:bg-green-950/50 dark:text-green-200",
    };
  }
  if (state === "unused") {
    return {
      label: "未引用",
      className: "bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-200",
    };
  }
  return null;
}

function buildSourceChunkHref(source: SourceInfo) {
  if (!source.document_id) return "";
  const params = new URLSearchParams({ document_id: source.document_id });
  if (source.chunk_id) params.set("chunk_id", source.chunk_id);
  if (typeof source.chunk_index === "number") params.set("chunk_index", String(source.chunk_index));
  return `/documents?${params.toString()}`;
}

function buildEvidenceChunkHref(item: EvidenceItem) {
  if (!item.document_id) return "";
  const params = new URLSearchParams({ document_id: item.document_id });
  if (item.chunk_id) params.set("chunk_id", item.chunk_id);
  if (typeof item.chunk_index === "number") params.set("chunk_index", String(item.chunk_index));
  return `/documents?${params.toString()}`;
}

function buildCitationEvidenceChunkHref(item: CitationEvidenceRef) {
  if (!item.document_id) return "";
  const params = new URLSearchParams({ document_id: item.document_id });
  if (item.chunk_id) params.set("chunk_id", item.chunk_id);
  if (typeof item.chunk_index === "number") params.set("chunk_index", String(item.chunk_index));
  return `/documents?${params.toString()}`;
}

function formatOcrConfidence(value?: number | null) {
  if (typeof value !== "number") return "";
  const percent = value <= 1 ? value * 100 : value;
  return `置信度 ${Math.round(percent)}%`;
}

function formatOcrImageRef(image: OcrImageRef, index: number) {
  const bits = [];
  if (typeof image.page === "number") bits.push(`第 ${image.page} 页`);
  if (typeof image.image_index === "number") bits.push(`图片 ${image.image_index}`);
  const confidence = formatOcrConfidence(image.confidence);
  if (confidence) bits.push(confidence);
  if (typeof image.line_count === "number") bits.push(`${image.line_count} 行`);
  if (typeof image.width === "number" && typeof image.height === "number") {
    bits.push(`${image.width}x${image.height}`);
  }
  if (image.target) bits.push(image.target);
  if (image.low_confidence) bits.push("低置信");
  if (image.text_preview) bits.push(image.text_preview);
  return bits.join(" · ") || `图片 ${index + 1}`;
}

function formatTableSourceRef(source: TableSourceRef, index: number) {
  const bits = [];
  if (typeof source.page === "number" && typeof source.page_end === "number" && source.page_end !== source.page) {
    bits.push(`第 ${source.page}-${source.page_end} 页`);
  } else if (typeof source.page === "number") {
    bits.push(`第 ${source.page} 页`);
  }
  if (typeof source.table_index === "number") bits.push(`表格 ${source.table_index}`);
  if (source.caption) bits.push(source.caption);
  else if (source.title) bits.push(source.title);
  if (source.type) bits.push(source.type);
  if (typeof source.row_count === "number" && typeof source.column_count === "number") {
    bits.push(`${source.row_count}x${source.column_count}`);
  }
  if (source.source) bits.push(source.source);
  if (source.target) bits.push(source.target);
  return bits.join(" · ") || `表格来源 ${index + 1}`;
}

function EvidenceArtifactPreview({ artifact }: { artifact?: EvidenceArtifact | null }) {
  if (!artifact) return null;

  if (artifact.type === "table") {
    const headers = artifact.headers || [];
    const visibleHeaders = headers.slice(0, 5);
    const rows = (artifact.rows || []).slice(0, 4);
    const sources = artifact.sources || [];
    const sourceBadges =
      sources.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-1">
          {sources.map((source, index) => (
            <span
              key={`${source.page ?? "page"}-${source.table_index ?? "table"}-${index}`}
              className="rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-800 dark:border-blue-800/60 dark:bg-blue-950/40 dark:text-blue-100"
            >
              {formatTableSourceRef(source, index)}
            </span>
          ))}
        </div>
      ) : null;
    if (headers.length > 0 && rows.length > 0) {
      return (
        <div className="mt-1">
          <div className="overflow-x-auto rounded border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-950">
            <table className="min-w-full text-left text-[11px]">
              <thead className="bg-gray-50 text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                <tr>
                  {visibleHeaders.map((header) => (
                    <th key={header || "empty-header"} className="whitespace-nowrap px-2 py-1 font-medium">
                      {header || "未命名列"}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {rows.map((row) => (
                  <tr key={row.join("|") || "empty-row"}>
                    {visibleHeaders.map((header, colIndex) => (
                      <td key={`${header || "empty-header"}-${row[colIndex] || "empty-cell"}`} className="max-w-[160px] truncate px-2 py-1 text-gray-600 dark:text-gray-300">
                        {row[colIndex] || ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {sourceBadges}
        </div>
      );
    }

    if (artifact.markdown) {
      return (
        <div className="mt-1">
          <pre className="max-h-28 overflow-auto rounded border border-gray-200 bg-white p-2 text-[11px] text-gray-600 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-300">
            {artifact.markdown}
          </pre>
          {sourceBadges}
        </div>
      );
    }

    return sourceBadges;
  }

  if (artifact.type === "image_ocr" || artifact.type === "ocr") {
    const images = artifact.images || [];
    return (
      <div className="mt-1 rounded border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
        {artifact.text && <div className="line-clamp-2 whitespace-pre-wrap">{artifact.text}</div>}
        {images.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {images.map((image, index) => (
              <span
                key={`${image.page ?? "page"}-${image.image_index ?? "image"}-${image.line_count ?? "lines"}-${image.text_length ?? "text"}`}
                className={`inline-block max-w-full truncate rounded border px-1.5 py-0.5 text-[10px] sm:max-w-[260px] ${
                  image.low_confidence
                    ? "border-red-200 bg-red-50 text-red-800 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-100"
                    : "border-amber-200 bg-white/70 dark:border-amber-800/60 dark:bg-amber-950/50"
                }`}
              >
                {formatOcrImageRef(image, index)}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (artifact.text && (artifact.type === "formula" || artifact.type === "code")) {
    return (
      <pre className="mt-1 max-h-24 overflow-auto rounded border border-gray-200 bg-white p-2 text-[11px] text-gray-600 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-300">
        {artifact.text}
      </pre>
    );
  }

  return null;
}

interface ChatMessageProps {
  message: MessageType;
  conversationId?: string;
  onEdit?: (messageId: string, newContent: string) => Promise<void>;
  onRegenerate?: (messageId: string) => Promise<void>;
  isGenerating?: boolean;
  assistantIconUrl?: string;
}

function ChatMessageImpl({
  message,
  conversationId,
  onEdit,
  onRegenerate,
  isGenerating = false,
  assistantIconUrl,
}: ChatMessageProps) {
  const isUser = message.role === "user";
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(message.content);
  const [isSaving, setIsSaving] = useState(false);
  const [activeCitationId, setActiveCitationId] = useState<string | null>(null);
  const [isEvidenceOpen, setIsEvidenceOpen] = useState(false);
  const messageRef = useRef<HTMLDivElement>(null);
  const evidenceRefs = useRef<Record<string, HTMLLIElement | null>>({});

  const citationIds = useMemo(() => {
    const ids = new Set<string>();
    for (const item of message.evidence || []) {
      if (item.id) ids.add(item.id);
    }
    for (const source of message.sources || []) {
      if (source.evidence_id) ids.add(source.evidence_id);
    }
    return [...ids];
  }, [message.evidence, message.sources]);

  const citationUseSets = useMemo(
    () => ({
      used: new Set(message.citation_quality?.valid_citation_ids || []),
      unused: new Set(message.citation_quality?.unused_evidence_ids || []),
    }),
    [message.citation_quality?.unused_evidence_ids, message.citation_quality?.valid_citation_ids],
  );

  const getCitationUseState = useCallback(
    (evidenceId?: string | null): CitationUseState => {
      if (!evidenceId) return "unknown";
      if (citationUseSets.used.has(evidenceId)) return "used";
      if (citationUseSets.unused.has(evidenceId)) return "unused";
      return "unknown";
    },
    [citationUseSets],
  );

  useEffect(() => {
    if (!isEditing) setEditContent(message.content);
  }, [message.content, isEditing]);

  const displayAssistantIconUrl = assistantIconUrl
    ? assistantIconUrl.startsWith("http")
      ? assistantIconUrl
      : `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${assistantIconUrl}`
    : null;

  const handleSave = async () => {
    if (!message.message_id || !onEdit || !conversationId) return;
    const next = editContent.trim();
    if (!next || next === message.content.trim()) {
      setIsEditing(false);
      return;
    }
    setIsSaving(true);
    try {
      await onEdit(message.message_id, next);
      setIsEditing(false);
    } finally {
      setIsSaving(false);
    }
  };

  const handleRegenerate = async () => {
    if (!isUser) return;
    if (!message.message_id || !onRegenerate || !conversationId) return;
    await onRegenerate(message.message_id);
  };

  const handleCitationClick = useCallback((citationId: string) => {
    setActiveCitationId(citationId);
    setIsEvidenceOpen(true);
    window.setTimeout(() => {
      evidenceRefs.current[citationId]?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }, 0);
  }, []);

  return (
    <div
      className={`flex w-full mb-4 sm:mb-6 items-start gap-2 sm:gap-3 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser && (
        <div className="flex-shrink-0 w-6 h-6 sm:w-8 sm:h-8 rounded-full overflow-hidden bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-md">
          {displayAssistantIconUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={displayAssistantIconUrl}
              alt="assistant"
              className="w-full h-full object-cover"
            />
          ) : (
            <span className="text-white text-xs sm:text-sm font-bold">AI</span>
          )}
        </div>
      )}

      <div
        className={`flex flex-col ${isUser ? "items-end" : "items-start"} max-w-[85%] sm:max-w-[85%] md:max-w-[75%]`}
      >
        <div
          ref={messageRef}
          className={`relative group rounded-xl px-3.5 sm:px-4 md:px-5 py-3 sm:py-3 md:py-4 shadow-lg border ${
            isUser
              ? "bg-blue-600 text-white border-blue-700 rounded-br-sm"
              : "bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border-gray-200 dark:border-gray-700 rounded-bl-sm"
          }`}
        >
          {isEditing ? (
            <div className="space-y-2">
              <textarea
                className="w-full min-h-[120px] p-2 rounded bg-white/90 text-gray-900 text-sm border border-gray-200"
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
              />
              <div className="flex gap-2 justify-end">
                <button
                  className="px-3 py-1.5 text-sm rounded bg-gray-200 text-gray-800 hover:bg-gray-300"
                  type="button"
                  onClick={() => {
                    setIsEditing(false);
                    setEditContent(message.content);
                  }}
                  disabled={isSaving}
                >
                  取消
                </button>
                <button
                  className="px-3 py-1.5 text-sm rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
                  type="button"
                  onClick={handleSave}
                  disabled={isSaving}
                >
                  保存
                </button>
              </div>
            </div>
          ) : (
            <>
              <FormattedMessage
                content={message.content}
                citationIds={isUser ? [] : citationIds}
                activeCitationId={activeCitationId}
                onCitationClick={isUser ? undefined : handleCitationClick}
              />
              {isGenerating &&
                !isUser &&
                message.content.trim().length === 0 && (
                  <div className="mt-2">
                    <ThinkingDots />
                  </div>
                )}

              {isUser &&
                message.message_id &&
                conversationId &&
                (onEdit || onRegenerate) && (
                  <div className="absolute -bottom-9 right-0 opacity-0 group-hover:opacity-100 transition-opacity flex gap-2">
                    {onEdit && (
                      <button
                        className="px-2 py-1 text-xs rounded bg-gray-100 text-gray-700 border border-gray-200 hover:bg-gray-200"
                        type="button"
                        onClick={() => setIsEditing(true)}
                      >
                        编辑
                      </button>
                    )}
                    {onRegenerate && (
                      <button
                        className="px-2 py-1 text-xs rounded bg-gray-100 text-gray-700 border border-gray-200 hover:bg-gray-200"
                        type="button"
                        onClick={handleRegenerate}
                      >
                        重新生成
                      </button>
                    )}
                  </div>
                )}
            </>
          )}
        </div>

        {message.timestamp && (
          <div className="text-[10px] sm:text-xs mt-1 sm:mt-2 px-1 text-gray-400 dark:text-gray-500">
            {formatChatTimestamp(message.timestamp)}
          </div>
        )}

        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-2 w-full text-xs text-gray-600 dark:text-gray-300">
            <div className="font-semibold mb-1">参考来源</div>
            <ul className="space-y-1">
              {message.sources.slice(0, 10).map((source) => {
                const chunkHref = buildSourceChunkHref(source);
                const useBadge = citationUseBadge(getCitationUseState(source.evidence_id));
                return (
                  <li
                    key={`${source.chunk_id || source.document_id || source.file_id || source.evidence_id || source.document_title || source.score}`}
                    className={`rounded border px-2 py-1 transition-colors ${
                      source.evidence_id && source.evidence_id === activeCitationId
                        ? "border-amber-400 bg-amber-50 dark:border-amber-500 dark:bg-amber-950/30"
                        : "border-gray-200 dark:border-gray-700"
                    }`}
                  >
                    <div className="flex min-w-0 items-center gap-1.5">
                      {source.evidence_id && (
                        <span className="shrink-0 rounded bg-gray-900 px-1.5 py-0.5 text-[10px] font-medium text-white dark:bg-gray-100 dark:text-gray-900">
                          {source.evidence_id}
                        </span>
                      )}
                      {source.content_type && (
                        <span className="shrink-0 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-700 dark:bg-blue-950 dark:text-blue-200">
                          {evidenceTypeLabel[source.content_type] || source.content_type}
                        </span>
                      )}
                      {useBadge && (
                        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] ${useBadge.className}`}>
                          {useBadge.label}
                        </span>
                      )}
                      <span className="truncate font-medium">
                        {source.document_title || source.document_id || source.chunk_id || "来源"}
                      </span>
                      {typeof source.score === "number" && (
                        <span className="shrink-0 text-gray-400">{source.score.toFixed(3)}</span>
                      )}
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-gray-500 dark:text-gray-400">
                      {formatSourceLocation(source) && <span>{formatSourceLocation(source)}</span>}
                      {chunkHref && (
                        <Link href={chunkHref} className="font-medium text-blue-600 hover:text-blue-700 dark:text-blue-300 dark:hover:text-blue-200">
                          查看切块
                        </Link>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {!isUser && message.evidence && message.evidence.length > 0 && (
          <details
            className="mt-2 w-full text-xs text-gray-600 dark:text-gray-300"
            open={isEvidenceOpen}
            onToggle={(event) => setIsEvidenceOpen(event.currentTarget.open)}
          >
            <summary className="cursor-pointer font-semibold">检索证据</summary>
            <ul className="mt-1 space-y-1">
              {message.evidence.slice(0, 8).map((item) => {
                const chunkHref = buildEvidenceChunkHref(item);
                const useBadge = citationUseBadge(getCitationUseState(item.id));
                return (
                  <li
                    key={item.id}
                    ref={(node) => {
                      evidenceRefs.current[item.id] = node;
                    }}
                    className={`rounded border px-2 py-1 transition-colors ${
                      item.id === activeCitationId
                        ? "border-amber-400 bg-amber-50 dark:border-amber-500 dark:bg-amber-950/30"
                        : "border-gray-200 dark:border-gray-700"
                    }`}
                  >
                    <div className="flex min-w-0 items-center gap-1.5">
                      <span className="shrink-0 rounded bg-gray-900 px-1.5 py-0.5 text-[10px] font-medium text-white dark:bg-gray-100 dark:text-gray-900">
                        {item.id}
                      </span>
                      <span className="shrink-0 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-700 dark:bg-blue-950 dark:text-blue-200">
                        {evidenceTypeLabel[getEvidenceType(item)] || getEvidenceType(item)}
                      </span>
                      {useBadge && (
                        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] ${useBadge.className}`}>
                          {useBadge.label}
                        </span>
                      )}
                      <span className="truncate font-medium">
                        {item.document_title || item.document_id || item.file_id || "证据"}
                      </span>
                      {typeof item.score === "number" && (
                        <span className="shrink-0 text-gray-400">{item.score.toFixed(3)}</span>
                      )}
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-gray-500 dark:text-gray-400">
                      {formatEvidenceLocation(item) && <span>{formatEvidenceLocation(item)}</span>}
                      <span>{item.retrieval_type}</span>
                      {chunkHref && (
                        <Link href={chunkHref} className="font-medium text-blue-600 hover:text-blue-700 dark:text-blue-300 dark:hover:text-blue-200">
                          查看切块
                        </Link>
                      )}
                    </div>
                    <div className="line-clamp-2 text-gray-500 dark:text-gray-400">
                      {item.metadata?.preview || item.text}
                    </div>
                    {formatArtifactQualityWarnings(item) && (
                      <div className="mt-1 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-100">
                        {formatArtifactQualityWarnings(item)}
                      </div>
                    )}
                    <EvidenceArtifactPreview artifact={item.metadata?.artifact} />
                  </li>
                );
              })}
            </ul>
          </details>
        )}

        {!isUser &&
          message.citation_warnings &&
          message.citation_warnings.length > 0 && (
            <div className="mt-2 w-full text-xs text-amber-700 dark:text-amber-300">
              {message.citation_warnings.join("；")}
            </div>
          )}

        {!isUser && formatCitationQuality(message.citation_quality) && (
          <div className="mt-1 w-full text-xs text-gray-500 dark:text-gray-400">
            {formatCitationQuality(message.citation_quality)}
          </div>
        )}

        {!isUser && message.citation_quality?.unreferenced_top_evidence?.length ? (
          <div className="mt-2 w-full rounded border border-amber-200 bg-amber-50/70 px-2 py-1.5 text-xs text-amber-900 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-100">
            <div className="mb-1 font-medium">未引用高分证据</div>
            <div className="space-y-1">
              {message.citation_quality.unreferenced_top_evidence.slice(0, 3).map((item) => {
                const chunkHref = buildCitationEvidenceChunkHref(item);
                const location = formatCitationEvidenceLocation(item);
                const typeLabel = item.content_type ? evidenceTypeLabel[item.content_type] || item.content_type : "";
                return (
                  <div
                    key={`${item.id}-${item.chunk_id || item.chunk_index || item.document_id || item.score}`}
                    className={`rounded border px-2 py-1 ${
                      item.id === activeCitationId
                        ? "border-amber-500 bg-white dark:border-amber-400 dark:bg-amber-950/50"
                        : "border-amber-200/80 bg-white/70 dark:border-amber-800/50 dark:bg-amber-950/20"
                    }`}
                  >
                    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                      <span className="rounded bg-amber-700 px-1.5 py-0.5 text-[10px] font-medium text-white dark:bg-amber-200 dark:text-amber-950">
                        {item.id}
                      </span>
                      {typeLabel && (
                        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800 dark:bg-amber-900/50 dark:text-amber-100">
                          {typeLabel}
                        </span>
                      )}
                      <span className="min-w-0 flex-1 truncate font-medium">
                        {item.document_title || item.document_id || item.chunk_id || "证据"}
                      </span>
                      {typeof item.score === "number" && (
                        <span className="shrink-0 text-amber-700/80 dark:text-amber-200/80">{item.score.toFixed(3)}</span>
                      )}
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-amber-800/80 dark:text-amber-100/80">
                      {location && <span>{location}</span>}
                      {item.retrieval_type && <span>{item.retrieval_type}</span>}
                      <button
                        type="button"
                        onClick={() => handleCitationClick(item.id)}
                        className="font-medium text-blue-700 hover:text-blue-800 dark:text-blue-200 dark:hover:text-blue-100"
                      >
                        定位证据
                      </button>
                      {chunkHref && (
                        <Link href={chunkHref} className="font-medium text-blue-700 hover:text-blue-800 dark:text-blue-200 dark:hover:text-blue-100">
                          查看切块
                        </Link>
                      )}
                    </div>
                    {item.preview && (
                      <div className="mt-0.5 line-clamp-2 text-[11px] text-amber-900/70 dark:text-amber-100/70">
                        {item.preview}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {!isUser && formatEvidenceQuality(message.evidence_quality) && (
          <div
            className={`mt-1 w-full text-xs ${
              message.evidence_quality?.status === "warn"
                ? "text-amber-700 dark:text-amber-300"
                : "text-gray-500 dark:text-gray-400"
            }`}
          >
            {formatEvidenceQuality(message.evidence_quality)}
          </div>
        )}

        {/* RAG 评测指标（折叠，仅助手消息且存在检索/指标时展示） */}
        {!isUser &&
          (message.rag_metrics ||
            (message.sources && message.sources.length > 0)) && (
            <RAGEvaluationPanel
              metrics={message.rag_metrics}
              sourceCount={message.sources?.length ?? 0}
            />
          )}
      </div>
    </div>
  );
}

const ChatMessage = memo(ChatMessageImpl);
export default ChatMessage;
