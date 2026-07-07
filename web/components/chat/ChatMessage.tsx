"use client";

import RAGEvaluationPanel from "@/components/chat/RAGEvaluationPanel";
import FormattedMessage from "@/components/message/FormattedMessage";
import ThinkingDots from "@/components/message/ThinkingDots";
import BboxMiniMap from "@/components/ui/BboxMiniMap";
import { buildDocumentPreviewUrl } from "@/lib/api";
import { formatChatTimestamp } from "@/lib/timezone";
import type { ChatMessage as MessageType, CitationEvidenceAudit, CitationEvidenceRef, CitationQuality, EvidenceArtifact, EvidenceArtifactQuality, EvidenceItem, EvidenceQuality, OcrImageRef, SourceInfo, SourceLocatorAnchor, SourceLocatorSummary, TableSourceRef } from "@/types/chat";
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

function formatCitationAuditLocation(item: CitationEvidenceAudit) {
  const pageStart = item.page_start ?? item.page ?? null;
  const pageEnd = item.page_end ?? item.page ?? null;
  const pages =
    pageStart && pageEnd && pageStart !== pageEnd
      ? `第 ${pageStart}-${pageEnd} 页`
      : pageStart
        ? `第 ${pageStart} 页`
        : "";
  const chunk = typeof item.chunk_index === "number" ? `chunk ${item.chunk_index}` : "";
  return [pages, chunk].filter(Boolean).join(" · ");
}

function formatSourceLocatorSummary(locator?: SourceLocatorSummary | null) {
  if (!locator || !locator.anchor_count) return "";
  const bits: string[] = [];
  if (typeof locator.page_start === "number" && typeof locator.page_end === "number" && locator.page_end !== locator.page_start) {
    bits.push(`第 ${locator.page_start}-${locator.page_end} 页`);
  } else if (typeof locator.page_start === "number") {
    bits.push(`第 ${locator.page_start} 页`);
  }
  if (typeof locator.char_start === "number" && typeof locator.char_end === "number") {
    bits.push(`字符 ${locator.char_start}-${locator.char_end}`);
  }
  if (locator.has_table_source) bits.push("表格来源");
  if (locator.has_image_source) bits.push("图片来源");
  if (locator.has_bbox) bits.push("bbox");
  bits.push(`${locator.anchor_count} anchors`);
  return bits.join(" · ");
}

const sourceLocatorAnchorTypeLabel: Record<string, string> = {
  page_range: "页码",
  char_range: "字符",
  table: "表格",
  image: "图片",
  section: "章节",
};

const citationRiskReasonLabel: Record<string, string> = {
  missing_source_locator: "缺来源定位",
  artifact_warning: "解析需复核",
  low_confidence_ocr: "低置信OCR",
  quality_note: "质量提示",
};

function formatSourceLocatorAnchor(anchor: SourceLocatorAnchor, index: number) {
  const bits: string[] = [];
  const type = anchor.type ? sourceLocatorAnchorTypeLabel[anchor.type] || anchor.type : `锚点 ${index + 1}`;
  bits.push(type);
  if (typeof anchor.page_start === "number" && typeof anchor.page_end === "number" && anchor.page_end !== anchor.page_start) {
    bits.push(`第 ${anchor.page_start}-${anchor.page_end} 页`);
  } else if (typeof anchor.page === "number") {
    bits.push(`第 ${anchor.page} 页`);
  } else if (typeof anchor.page_start === "number") {
    bits.push(`第 ${anchor.page_start} 页`);
  }
  if (typeof anchor.char_start === "number" && typeof anchor.char_end === "number") {
    bits.push(`字符 ${anchor.char_start}-${anchor.char_end}`);
  }
  if (typeof anchor.table_index === "number") bits.push(`表格 ${anchor.table_index}`);
  if (typeof anchor.image_index === "number") bits.push(`图片 ${anchor.image_index}`);
  if (typeof anchor.confidence === "number") bits.push(formatOcrConfidence(anchor.confidence));
  if (anchor.low_confidence) bits.push("低置信");
  if (anchor.caption) bits.push(anchor.caption);
  else if (anchor.title) bits.push(anchor.title);
  if (anchor.source) bits.push(anchor.source);
  if (anchor.target) bits.push(anchor.target);
  if (anchor.text_preview) bits.push(anchor.text_preview);
  return bits.filter(Boolean).join(" · ");
}

function SourceLocatorAnchorPreview({ locator }: { locator?: SourceLocatorSummary | null }) {
  const anchors = (locator?.anchors || []).filter((anchor) => anchor && typeof anchor === "object").slice(0, 3);
  if (!anchors.length) return null;
  const total = typeof locator?.anchor_count === "number" ? Math.max(locator.anchor_count, anchors.length) : anchors.length;
  const remaining = Math.max(total - anchors.length, 0);

  return (
    <div className="mt-1 rounded border border-emerald-100 bg-emerald-50/60 px-2 py-1 text-[11px] text-emerald-900 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-100">
      <div className="mb-1 font-medium">定位锚点</div>
      <div className="space-y-1">
        {anchors.map((anchor, index) => (
          <div key={`${anchor.type || "anchor"}-${anchor.page ?? anchor.page_start ?? "page"}-${anchor.table_index ?? anchor.image_index ?? index}`} className="flex min-w-0 flex-wrap items-start gap-x-2 gap-y-1">
            <span className="min-w-0 flex-1 break-words">{formatSourceLocatorAnchor(anchor, index)}</span>
            {anchor.bbox ? (
              <BboxMiniMap bbox={anchor.bbox} frameWidth={anchor.width} frameHeight={anchor.height} compact />
            ) : null}
          </div>
        ))}
        {remaining > 0 && <div className="text-emerald-700 dark:text-emerald-200">还有 {remaining} 个锚点</div>}
      </div>
    </div>
  );
}

function getEvidenceType(item: EvidenceItem) {
  return item.metadata?.content_type || "text";
}

function formatCitationQuality(quality?: CitationQuality | null) {
  if (!quality || typeof quality.evidence_count !== "number" || quality.evidence_count <= 0) return "";
  const bits = [];
  if (quality.risk_level === "high") {
    bits.push("引用风险高");
  } else if (quality.risk_level === "medium") {
    bits.push("引用需复核");
  }
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
  if (quality.cited_missing_source_locator_ids?.length) {
    bits.push(`引用缺定位 ${quality.cited_missing_source_locator_ids.join(", ")}`);
  }
  if (quality.cited_artifact_warning_ids?.length) {
    bits.push(`引用需复核 ${quality.cited_artifact_warning_ids.join(", ")}`);
  }
  if (quality.cited_low_confidence_ocr_ids?.length) {
    bits.push(`低置信引用 ${quality.cited_low_confidence_ocr_ids.join(", ")}`);
  }
  if (quality.cited_quality_note_ids?.length) {
    bits.push(`质量提示引用 ${quality.cited_quality_note_ids.join(", ")}`);
  }
  if (quality.unreferenced_top_evidence_ids?.length) {
    bits.push(`未引用高分证据 ${quality.unreferenced_top_evidence_ids.join(", ")}`);
  }
  return bits.join(" · ");
}

function formatCitationRecommendations(quality?: CitationQuality | null) {
  if (!quality?.recommendations?.length) return "";
  return quality.recommendations.slice(0, 3).join("；");
}

function formatEvidenceQuality(quality?: EvidenceQuality | null) {
  if (!quality || typeof quality.evidence_count !== "number" || quality.evidence_count <= 0) return "";
  const bits = [];
  if (typeof quality.structured_artifact_coverage === "number") {
    bits.push(`结构化证据 ${Math.round(quality.structured_artifact_coverage * 100)}%`);
  } else if (typeof quality.artifact_coverage === "number") {
    bits.push(`artifact ${Math.round(quality.artifact_coverage * 100)}%`);
  }
  if (typeof quality.source_locator_coverage === "number") {
    bits.push(`定位 ${Math.round(quality.source_locator_coverage * 100)}%`);
  }
  if ((quality.structured_missing_source_locator_count || 0) > 0) {
    bits.push(`结构化缺定位 ${quality.structured_missing_source_locator_count}`);
  } else if ((quality.missing_source_locator_count || 0) > 0) {
    bits.push(`缺定位 ${quality.missing_source_locator_count}`);
  }
  if ((quality.bbox_source_locator_count || 0) > 0) {
    bits.push(`bbox定位 ${quality.bbox_source_locator_count}`);
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

function qualityNotesFromSource(source: SourceInfo) {
  const notes = (source.quality_notes || []).map((note) => String(note).trim()).filter(Boolean);
  if (notes.length) return notes;
  const quality = source.artifact_quality;
  return quality?.status === "warn" && quality.warnings?.length ? quality.warnings : [];
}

function qualityNotesFromEvidence(item: EvidenceItem) {
  const notes = (item.metadata?.quality_notes || []).map((note) => String(note).trim()).filter(Boolean);
  if (notes.length) return notes;
  const warnings = formatArtifactQualityWarnings(item);
  return warnings ? [warnings] : [];
}

function qualityNotesFromCitationEvidence(item: CitationEvidenceRef) {
  const notes = (item.quality_notes || []).map((note) => String(note).trim()).filter(Boolean);
  const quality = item.artifact_quality;
  if (!notes.length && quality?.status === "warn" && quality.warnings?.length) return quality.warnings;
  return notes;
}

function QualityNoteList({ notes }: { notes: string[] }) {
  if (!notes.length) return null;
  return (
    <div className="mt-1 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-100">
      <div className="font-medium">质量提示</div>
      <ul className="mt-1 list-disc space-y-0.5 pl-4">
        {notes.slice(0, 4).map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </div>
  );
}

function artifactIssueFeature(quality?: EvidenceArtifactQuality | null) {
  if (!quality || quality.status !== "warn") return "";
  if (quality.table_missing_structure) return "table_missing_structure";
  if (quality.table_missing_source) return "table_missing_source";
  if (quality.ocr_missing_source) return "ocr_missing_source";
  if (quality.ocr_low_confidence_source_count > 0) return "ocr_low_confidence";
  return "artifact_issue";
}

function citationEvidenceIssueFeature(item: CitationEvidenceRef) {
  const reasons = item.risk_reasons || [];
  if (reasons.includes("missing_source_locator")) return "structured_missing_source_locator";
  if (reasons.includes("low_confidence_ocr")) return "ocr_low_confidence";
  return artifactIssueFeature(item.artifact_quality);
}

function formatCitationEvidenceRiskReasons(item: CitationEvidenceRef) {
  return (item.risk_reasons || []).map((reason) => citationRiskReasonLabel[reason] || reason).filter(Boolean);
}

function formatCitationAuditRiskReasons(item: CitationEvidenceAudit) {
  return (item.risk_reasons || []).map((reason) => citationRiskReasonLabel[reason] || reason).filter(Boolean);
}

function citationAuditIssueFeature(item: CitationEvidenceAudit) {
  const reasons = item.risk_reasons || [];
  if (reasons.includes("missing_source_locator")) return "structured_missing_source_locator";
  if (reasons.includes("low_confidence_ocr")) return "ocr_low_confidence";
  if (reasons.includes("artifact_warning")) return "artifact_issue";
  return "";
}

function formatCitationAuditLocator(item: CitationEvidenceAudit) {
  if (!item.has_source_locator) return "缺少来源定位";
  const bits = [`${item.source_anchor_count || 0} anchors`];
  if (item.has_table_source) bits.push("表格来源");
  if (item.has_image_source) bits.push("图片来源");
  if (item.has_bbox) bits.push("bbox");
  return bits.join(" · ");
}

function appendChunkInspectorContext(params: URLSearchParams, contentType?: string | null, feature?: string | null) {
  const normalizedType = contentType?.trim();
  const normalizedFeature = feature?.trim();
  if (normalizedType) params.set("content_type", normalizedType);
  if (normalizedFeature) params.set("feature", normalizedFeature);
}

function appendEvidenceDeepLinkContext(params: URLSearchParams, evidenceId?: string | null) {
  const normalizedEvidenceId = evidenceId?.trim();
  if (normalizedEvidenceId) params.set("evidence_id", normalizedEvidenceId);
  params.set("context_window", "6");
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
  appendChunkInspectorContext(params, source.content_type || source.artifact?.type || null, null);
  appendEvidenceDeepLinkContext(params, source.evidence_id);
  return `/documents?${params.toString()}`;
}

function buildEvidenceChunkHref(item: EvidenceItem) {
  if (!item.document_id) return "";
  const params = new URLSearchParams({ document_id: item.document_id });
  if (item.chunk_id) params.set("chunk_id", item.chunk_id);
  if (typeof item.chunk_index === "number") params.set("chunk_index", String(item.chunk_index));
  appendChunkInspectorContext(params, getEvidenceType(item), artifactIssueFeature(item.metadata?.artifact_quality));
  appendEvidenceDeepLinkContext(params, item.id);
  return `/documents?${params.toString()}`;
}

function buildCitationEvidenceChunkHref(item: CitationEvidenceRef) {
  if (!item.document_id) return "";
  const params = new URLSearchParams({ document_id: item.document_id });
  if (item.chunk_id) params.set("chunk_id", item.chunk_id);
  if (typeof item.chunk_index === "number") params.set("chunk_index", String(item.chunk_index));
  appendChunkInspectorContext(params, item.content_type || null, citationEvidenceIssueFeature(item));
  appendEvidenceDeepLinkContext(params, item.id);
  return `/documents?${params.toString()}`;
}

function buildCitationAuditChunkHref(item: CitationEvidenceAudit) {
  if (!item.document_id) return "";
  const params = new URLSearchParams({ document_id: item.document_id });
  if (item.chunk_id) params.set("chunk_id", item.chunk_id);
  if (typeof item.chunk_index === "number") params.set("chunk_index", String(item.chunk_index));
  appendChunkInspectorContext(params, item.content_type || null, citationAuditIssueFeature(item));
  appendEvidenceDeepLinkContext(params, item.id);
  return `/documents?${params.toString()}`;
}

function formatOcrConfidence(value?: number | null) {
  if (typeof value !== "number") return "";
  const percent = value <= 1 ? value * 100 : value;
  return `置信度 ${Math.round(percent)}%`;
}

function formatLocatorValue(value: unknown) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map((item) => String(item)).join(", ");
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
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
  if (image.bbox) bits.push(`bbox ${formatLocatorValue(image.bbox)}`);
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
  if (source.bbox) bits.push(`bbox ${formatLocatorValue(source.bbox)}`);
  return bits.join(" · ") || `表格来源 ${index + 1}`;
}

function TableSourceLocator({ sources }: { sources: TableSourceRef[] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-1 border-t border-blue-100 pt-1.5 text-[10px] text-blue-900 dark:border-blue-900/60 dark:text-blue-100">
      <div className="mb-1 font-medium">来源定位</div>
      <div className="space-y-1">
        {sources.map((source, index) => (
          <div key={`${source.page ?? "page"}-${source.table_index ?? "table"}-${index}`} className="flex min-w-0 flex-wrap gap-x-1.5 gap-y-1">
            <span className="shrink-0 rounded bg-white px-1 py-0.5 text-blue-700 dark:bg-gray-900 dark:text-blue-200">
              来源 {index + 1}
            </span>
            <span className="min-w-0 break-all">{formatTableSourceRef(source, index)}</span>
            {source.bbox ? <BboxMiniMap bbox={source.bbox} compact className="mt-1" /> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function OcrSourceLocator({ images }: { images: OcrImageRef[] }) {
  if (!images.length) return null;
  return (
    <div className="mt-1 border-t border-amber-200 pt-1.5 text-[10px] text-amber-900 dark:border-amber-800/60 dark:text-amber-100">
      <div className="mb-1 font-medium">图片来源</div>
      <div className="space-y-1">
        {images.map((image, index) => (
          <div
            key={`${image.page ?? "page"}-${image.image_index ?? "image"}-${index}`}
            className={`flex min-w-0 flex-wrap gap-x-1.5 gap-y-1 rounded px-1 py-0.5 ${
              image.low_confidence ? "bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-100" : "bg-amber-50/70 dark:bg-amber-950/30"
            }`}
          >
            <span className="shrink-0 rounded bg-white px-1 py-0.5 text-amber-700 dark:bg-gray-900 dark:text-amber-200">
              图片 {typeof image.image_index === "number" ? image.image_index : index + 1}
            </span>
            <span className="min-w-0 break-all">{formatOcrImageRef(image, index)}</span>
            {image.bbox ? (
              <BboxMiniMap bbox={image.bbox} frameWidth={image.width} frameHeight={image.height} compact className="mt-1" />
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function EvidenceArtifactPreview({ artifact }: { artifact?: EvidenceArtifact | null }) {
  if (!artifact) return null;

  if (artifact.type === "table") {
    const headers = artifact.headers || [];
    const visibleHeaders = headers.slice(0, 5);
    const rows = (artifact.rows || []).slice(0, 4);
    const sources = artifact.sources || [];
    const sourceLocator = <TableSourceLocator sources={sources} />;
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
          {sourceLocator}
        </div>
      );
    }

    if (artifact.markdown) {
      return (
        <div className="mt-1">
          <pre className="max-h-28 overflow-auto rounded border border-gray-200 bg-white p-2 text-[11px] text-gray-600 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-300">
            {artifact.markdown}
          </pre>
          {sourceLocator}
        </div>
      );
    }

    return sourceLocator;
  }

  if (artifact.type === "image_ocr" || artifact.type === "ocr") {
    const images = artifact.images || [];
    return (
      <div className="mt-1 rounded border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
        {artifact.text && <div className="line-clamp-2 whitespace-pre-wrap">{artifact.text}</div>}
        <OcrSourceLocator images={images} />
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
                const previewHref = buildDocumentPreviewUrl(source.document_id, source.page_start || source.page || null);
                const sourceLocatorSummary = formatSourceLocatorSummary(source.source_locator);
                const useBadge = citationUseBadge(getCitationUseState(source.evidence_id));
                const qualityNotes = qualityNotesFromSource(source);
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
                      {previewHref && (
                        <a href={previewHref} target="_blank" rel="noreferrer" className="font-medium text-blue-600 hover:text-blue-700 dark:text-blue-300 dark:hover:text-blue-200">
                          打开原文
                        </a>
                      )}
                    </div>
                    {sourceLocatorSummary && (
                      <div className="mt-1 rounded border border-emerald-100 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-100">
                        来源定位：{sourceLocatorSummary}
                      </div>
                    )}
                    <SourceLocatorAnchorPreview locator={source.source_locator} />
                    <QualityNoteList notes={qualityNotes} />
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
                const previewHref = buildDocumentPreviewUrl(item.document_id, item.metadata?.page_start || item.page || null);
                const sourceLocatorSummary = formatSourceLocatorSummary(item.metadata?.source_locator);
                const useBadge = citationUseBadge(getCitationUseState(item.id));
                const qualityNotes = qualityNotesFromEvidence(item);
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
                      {previewHref && (
                        <a href={previewHref} target="_blank" rel="noreferrer" className="font-medium text-blue-600 hover:text-blue-700 dark:text-blue-300 dark:hover:text-blue-200">
                          打开原文
                        </a>
                      )}
                    </div>
                    {sourceLocatorSummary && (
                      <div className="mt-1 rounded border border-emerald-100 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-100">
                        来源定位：{sourceLocatorSummary}
                      </div>
                    )}
                    <SourceLocatorAnchorPreview locator={item.metadata?.source_locator} />
                    <div className="line-clamp-2 text-gray-500 dark:text-gray-400">
                      {item.metadata?.preview || item.text}
                    </div>
                    <QualityNoteList notes={qualityNotes} />
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
        {!isUser && formatCitationRecommendations(message.citation_quality) && (
          <div className="mt-1 w-full rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-800 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-100">
            {formatCitationRecommendations(message.citation_quality)}
          </div>
        )}

        {!isUser && message.citation_quality?.evidence_citation_audit?.length ? (
          <div className="mt-2 w-full rounded border border-slate-200 bg-slate-50/80 px-2 py-1.5 text-xs text-slate-800 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-100">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="font-medium">证据引用审计</span>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">
                {message.citation_quality.evidence_citation_audit.length} 条
              </span>
            </div>
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {message.citation_quality.evidence_citation_audit.slice(0, 6).map((item) => {
                const chunkHref = buildCitationAuditChunkHref(item);
                const location = formatCitationAuditLocation(item);
                const locator = formatCitationAuditLocator(item);
                const riskLabels = formatCitationAuditRiskReasons(item);
                const useBadge = citationUseBadge(getCitationUseState(item.id));
                const typeLabel = item.content_type ? evidenceTypeLabel[item.content_type] || item.content_type : "";
                return (
                  <div
                    key={`${item.id}-${item.chunk_id || item.chunk_index || item.document_id || item.score}-audit`}
                    className={`rounded border px-2 py-1 ${
                      item.id === activeCitationId
                        ? "border-blue-400 bg-white dark:border-blue-300 dark:bg-slate-950/60"
                        : "border-slate-200 bg-white/80 dark:border-slate-700 dark:bg-slate-950/30"
                    }`}
                  >
                    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                      <span className="rounded bg-slate-900 px-1.5 py-0.5 text-[10px] font-medium text-white dark:bg-slate-100 dark:text-slate-950">
                        {item.id}
                      </span>
                      {typeLabel && (
                        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-700 dark:bg-blue-950 dark:text-blue-200">
                          {typeLabel}
                        </span>
                      )}
                      {useBadge && (
                        <span className={`rounded px-1.5 py-0.5 text-[10px] ${useBadge.className}`}>
                          {useBadge.label}
                        </span>
                      )}
                      {riskLabels.map((label) => (
                        <span key={`${item.id}-${label}-audit-risk`} className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800 dark:bg-amber-900/50 dark:text-amber-100">
                          {label}
                        </span>
                      ))}
                      {typeof item.score === "number" && (
                        <span className="ml-auto shrink-0 text-[11px] text-slate-500 dark:text-slate-400">
                          {item.score.toFixed(3)}
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                      {location && <span>{location}</span>}
                      {item.retrieval_type && <span>{item.retrieval_type}</span>}
                      <span>{locator}</span>
                      {item.artifact_quality_status && <span>artifact {item.artifact_quality_status}</span>}
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px]">
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
                    {item.quality_notes?.length ? <QualityNoteList notes={item.quality_notes} /> : null}
                  </div>
                );
              })}
            </div>
            {message.citation_quality.evidence_citation_audit.length > 6 && (
              <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                还有 {message.citation_quality.evidence_citation_audit.length - 6} 条证据可在检索证据中查看
              </div>
            )}
          </div>
        ) : null}

        {!isUser && message.citation_quality?.cited_risky_evidence?.length ? (
          <div className="mt-2 w-full rounded border border-rose-200 bg-rose-50/70 px-2 py-1.5 text-xs text-rose-900 dark:border-rose-800/60 dark:bg-rose-950/30 dark:text-rose-100">
            <div className="mb-1 font-medium">已引用需复核证据</div>
            <div className="space-y-1">
              {message.citation_quality.cited_risky_evidence.slice(0, 4).map((item) => {
                const chunkHref = buildCitationEvidenceChunkHref(item);
                const previewHref = buildDocumentPreviewUrl(item.document_id, item.page_start || item.page || null);
                const location = formatCitationEvidenceLocation(item);
                const sourceLocatorSummary = formatSourceLocatorSummary(item.source_locator);
                const typeLabel = item.content_type ? evidenceTypeLabel[item.content_type] || item.content_type : "";
                const riskLabels = formatCitationEvidenceRiskReasons(item);
                const qualityNotes = qualityNotesFromCitationEvidence(item);
                return (
                  <div
                    key={`${item.id}-${item.chunk_id || item.chunk_index || item.document_id || item.score}-risky`}
                    className={`rounded border px-2 py-1 ${
                      item.id === activeCitationId
                        ? "border-rose-500 bg-white dark:border-rose-400 dark:bg-rose-950/50"
                        : "border-rose-200/80 bg-white/70 dark:border-rose-800/50 dark:bg-rose-950/20"
                    }`}
                  >
                    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                      <span className="rounded bg-rose-700 px-1.5 py-0.5 text-[10px] font-medium text-white dark:bg-rose-200 dark:text-rose-950">
                        {item.id}
                      </span>
                      {typeLabel && (
                        <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] text-rose-800 dark:bg-rose-900/50 dark:text-rose-100">
                          {typeLabel}
                        </span>
                      )}
                      {riskLabels.map((label) => (
                        <span key={`${item.id}-${label}`} className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800 dark:bg-amber-900/50 dark:text-amber-100">
                          {label}
                        </span>
                      ))}
                      <span className="min-w-0 flex-1 truncate font-medium">
                        {item.document_title || item.document_id || item.chunk_id || "证据"}
                      </span>
                      {typeof item.score === "number" && (
                        <span className="shrink-0 text-rose-700/80 dark:text-rose-200/80">{item.score.toFixed(3)}</span>
                      )}
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-rose-800/80 dark:text-rose-100/80">
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
                      {previewHref && (
                        <a href={previewHref} target="_blank" rel="noreferrer" className="font-medium text-blue-700 hover:text-blue-800 dark:text-blue-200 dark:hover:text-blue-100">
                          打开原文
                        </a>
                      )}
                    </div>
                    {sourceLocatorSummary ? (
                      <div className="mt-1 rounded border border-emerald-100 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-100">
                        来源定位：{sourceLocatorSummary}
                      </div>
                    ) : (
                      <div className="mt-1 rounded border border-rose-200 bg-rose-100/70 px-2 py-0.5 text-[11px] text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/50 dark:text-rose-100">
                        缺少统一来源定位
                      </div>
                    )}
                    <SourceLocatorAnchorPreview locator={item.source_locator} />
                    {item.preview && (
                      <div className="mt-0.5 line-clamp-2 text-[11px] text-rose-900/70 dark:text-rose-100/70">
                        {item.preview}
                      </div>
                    )}
                    <QualityNoteList notes={qualityNotes} />
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {!isUser && message.citation_quality?.unreferenced_top_evidence?.length ? (
          <div className="mt-2 w-full rounded border border-amber-200 bg-amber-50/70 px-2 py-1.5 text-xs text-amber-900 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-100">
            <div className="mb-1 font-medium">未引用高分证据</div>
            <div className="space-y-1">
              {message.citation_quality.unreferenced_top_evidence.slice(0, 3).map((item) => {
                const chunkHref = buildCitationEvidenceChunkHref(item);
                const previewHref = buildDocumentPreviewUrl(item.document_id, item.page_start || item.page || null);
                const location = formatCitationEvidenceLocation(item);
                const sourceLocatorSummary = formatSourceLocatorSummary(item.source_locator);
                const typeLabel = item.content_type ? evidenceTypeLabel[item.content_type] || item.content_type : "";
                const qualityNotes = qualityNotesFromCitationEvidence(item);
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
                      {previewHref && (
                        <a href={previewHref} target="_blank" rel="noreferrer" className="font-medium text-blue-700 hover:text-blue-800 dark:text-blue-200 dark:hover:text-blue-100">
                          打开原文
                        </a>
                      )}
                    </div>
                    {sourceLocatorSummary && (
                      <div className="mt-1 rounded border border-emerald-100 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-100">
                        来源定位：{sourceLocatorSummary}
                      </div>
                    )}
                    <SourceLocatorAnchorPreview locator={item.source_locator} />
                    {item.preview && (
                      <div className="mt-0.5 line-clamp-2 text-[11px] text-amber-900/70 dark:text-amber-100/70">
                        {item.preview}
                      </div>
                    )}
                    <QualityNoteList notes={qualityNotes} />
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
