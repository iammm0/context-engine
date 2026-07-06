"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DocumentUpload from "@/components/document/DocumentUpload";
import Layout from "@/components/ui/Layout";
import LoadingProgress from "@/components/ui/LoadingProgress";
import Toast, { type ToastType } from "@/components/ui/Toast";
import type { KnowledgeSpace } from "@/lib/api";
import { apiClient, type Document, type DocumentChunkPreview, type DocumentDetail, type OcrImageRef, type ParseQualitySummary, type TableSourceRef } from "@/lib/api";
import { formatDateTime } from "@/lib/timezone";

const contentTypeLabel: Record<string, string> = {
  text: "文本",
  table: "表格",
  image_ocr: "图片OCR",
  ocr: "OCR",
  formula: "公式",
  code: "代码",
};

type ChunkFilterOption = {
  value: string;
  label: string;
  count?: number;
};

const chunkFeatureFilterBaseOptions: ChunkFilterOption[] = [
  { value: "all", label: "全部质量" },
  { value: "artifact_issue", label: "Artifact问题" },
  { value: "table_artifact_issue", label: "表格问题" },
  { value: "ocr_artifact_issue", label: "OCR问题" },
  { value: "table_missing_structure", label: "表格缺结构" },
  { value: "table_missing_source", label: "表格缺来源" },
  { value: "ocr_missing_source", label: "OCR缺来源" },
  { value: "ocr_low_confidence", label: "OCR低置信" },
  { value: "missing_anchor", label: "缺定位" },
  { value: "size_issue", label: "尺寸异常" },
];

const featureFlagLabel: Record<string, string> = {
  table: "表格",
  image_ocr: "OCR",
  formula: "公式",
  code: "代码",
  artifact_issue: "Artifact问题",
  table_artifact_issue: "表格问题",
  ocr_artifact_issue: "OCR问题",
  table_missing_structure: "表格缺结构",
  table_missing_source: "表格缺来源",
  ocr_missing_source: "OCR缺来源",
  ocr_low_confidence: "OCR低置信",
  missing_anchor: "缺定位",
  location_issue: "定位问题",
  short_chunk: "过短",
  large_chunk: "过长",
  size_issue: "尺寸异常",
};

type ChunkDeepLinkTarget = {
  documentId: string;
  chunkId?: string;
  chunkIndex?: number;
  contentType?: string;
  feature?: string;
};

type ParseQualityCheckItem = NonNullable<ParseQualitySummary["quality_checks"]>[number];
type QualityIssueChip = {
  feature: string;
  label: string;
  count: number;
};

function parseChunkDeepLinkTarget(): ChunkDeepLinkTarget | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  const documentId = params.get("document_id")?.trim();
  if (!documentId) return null;

  const chunkId = params.get("chunk_id")?.trim() || undefined;
  const rawChunkIndex = params.get("chunk_index");
  const parsedIndex = rawChunkIndex !== null ? Number.parseInt(rawChunkIndex, 10) : Number.NaN;
  const chunkIndex = Number.isFinite(parsedIndex) && parsedIndex >= 0 ? parsedIndex : undefined;
  const contentType = params.get("content_type")?.trim() || undefined;
  const feature = params.get("feature")?.trim() || undefined;
  return {
    documentId,
    chunkId,
    chunkIndex,
    contentType: contentType && contentType !== "all" ? contentType : undefined,
    feature: feature && feature !== "all" ? feature : undefined,
  };
}

function chunkTargetKey(target: ChunkDeepLinkTarget) {
  return [
    target.documentId,
    target.chunkId || "",
    typeof target.chunkIndex === "number" ? target.chunkIndex : "",
    target.contentType || "",
    target.feature || "",
  ].join(":");
}

function documentFromDetail(detail: DocumentDetail): Document {
  return {
    id: detail.id,
    title: detail.title,
    file_type: detail.file_type,
    file_size: detail.file_size,
    created_at: detail.created_at,
    status: detail.status,
    progress_percentage: detail.progress_percentage,
    current_stage: detail.current_stage,
    stage_details: detail.stage_details,
    parse_quality:
      detail.parse_quality ||
      ((detail.metadata?.parse_quality as ParseQualitySummary | undefined) ?? null),
  };
}

function isHighlightedChunk(chunk: DocumentChunkPreview, target: ChunkDeepLinkTarget | null) {
  if (!target) return false;
  if (target.chunkId && chunk.id === target.chunkId) return true;
  return typeof target.chunkIndex === "number" && chunk.chunk_index === target.chunkIndex;
}

function getChunkFilterOptions(quality?: ParseQualitySummary | null): ChunkFilterOption[] {
  const counts = quality?.content_type_counts || {};
  const orderedTypes = ["text", "table", "image_ocr", "ocr", "formula", "code"];
  const options: ChunkFilterOption[] = [{ value: "all", label: "全部" }];
  const seen = new Set<string>();

  for (const type of orderedTypes) {
    const count = counts[type];
    if (typeof count === "number" && count > 0) {
      options.push({ value: type, label: contentTypeLabel[type] || type, count });
      seen.add(type);
    }
  }

  for (const [type, count] of Object.entries(counts)) {
    if (!seen.has(type) && typeof count === "number" && count > 0) {
      options.push({ value: type, label: contentTypeLabel[type] || type, count });
    }
  }

  return options;
}

function getChunkFeatureFilterOptions(quality?: ParseQualitySummary | null): ChunkFilterOption[] {
  const counts: Record<string, number | undefined> = {
    artifact_issue: quality?.artifact_issue_count,
    table_artifact_issue: quality?.table_artifact_issue_count,
    ocr_artifact_issue: quality?.ocr_artifact_issue_count,
    table_missing_structure: quality?.table_artifact_missing_structure_count,
    table_missing_source: quality?.table_artifact_missing_source_count,
    ocr_missing_source: quality?.ocr_artifact_missing_source_count,
    ocr_low_confidence: quality?.ocr_artifact_low_confidence_source_count,
    missing_anchor: quality?.chunk_missing_anchor_count,
    size_issue: (quality?.chunk_short_count || 0) + (quality?.chunk_large_count || 0),
  };
  return chunkFeatureFilterBaseOptions.map((option) => ({
    ...option,
    count: option.value === "all" ? undefined : counts[option.value],
  }));
}

function formatChunkLocation(chunk: DocumentChunkPreview) {
  const pages =
    chunk.page_start && chunk.page_end && chunk.page_start !== chunk.page_end
      ? `第 ${chunk.page_start}-${chunk.page_end} 页`
      : chunk.page || chunk.page_start
        ? `第 ${chunk.page || chunk.page_start} 页`
        : "";
  const section = chunk.section_path?.length ? chunk.section_path.join(" / ") : "";
  return [pages, section].filter(Boolean).join(" · ") || "未定位";
}

function formatPercent(value?: number | null) {
  if (typeof value !== "number") return "-";
  return `${Math.round(value * 100)}%`;
}

function formatParseQualityLine(quality?: ParseQualitySummary | null) {
  if (!quality) return "";
  const bits = [];
  if (typeof quality.quality_score === "number") bits.push(`质量 ${quality.quality_score}/100`);
  if (typeof quality.chunk_count === "number") bits.push(`chunk ${quality.chunk_count}`);
  if (typeof quality.chunk_anchor_coverage === "number") bits.push(`定位 ${formatPercent(quality.chunk_anchor_coverage)}`);
  if (typeof quality.table_count === "number") bits.push(`表格 ${quality.table_count}`);
  if (typeof quality.image_count === "number") bits.push(`图片 ${quality.image_count}`);
  if (typeof quality.ocr_text_length === "number" && quality.ocr_text_length > 0) {
    bits.push(`OCR ${quality.ocr_text_length}字`);
  }
  if (typeof quality.ocr_avg_confidence === "number") bits.push(`OCR置信度 ${formatPercent(quality.ocr_avg_confidence)}`);
  return bits.join(" · ");
}

function parseRiskLabel(level?: string) {
  if (level === "high") return "高风险";
  if (level === "medium") return "需关注";
  if (level === "low") return "良好";
  return level || "未知";
}

function parseRiskClass(level?: string) {
  if (level === "high") return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-200";
  if (level === "medium") return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-200";
  if (level === "low") return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-200";
  return "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-200";
}

function parseCheckClass(status?: string) {
  if (status === "fail") return "border-red-400 text-red-800 dark:border-red-500 dark:text-red-100";
  if (status === "warn") return "border-amber-400 text-amber-800 dark:border-amber-500 dark:text-amber-100";
  return "border-green-400 text-green-800 dark:border-green-500 dark:text-green-100";
}

function parseCheckStatusLabel(status?: string) {
  if (status === "fail") return "异常";
  if (status === "warn") return "关注";
  if (status === "pass") return "正常";
  return status || "未知";
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
  if (typeof image.text_length === "number") bits.push(`${image.text_length} 字`);
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
    <div className="mt-2 border-t border-blue-100 pt-2 text-[11px] text-blue-900 dark:border-blue-900/60 dark:text-blue-100">
      <div className="mb-1 font-medium">来源定位</div>
      <div className="space-y-1">
        {sources.map((source, index) => (
          <div key={`${source.page ?? "page"}-${source.table_index ?? "table"}-${index}`} className="flex min-w-0 flex-wrap gap-x-2 gap-y-1">
            <span className="shrink-0 rounded bg-white px-1.5 py-0.5 text-blue-700 dark:bg-gray-900 dark:text-blue-200">
              来源 {index + 1}
            </span>
            <span className="min-w-0 break-all">{formatTableSourceRef(source, index)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function OcrSourceLocator({ images }: { images: OcrImageRef[] }) {
  if (!images.length) return null;
  return (
    <div className="mt-2 border-t border-amber-200 pt-2 text-[11px] text-amber-900 dark:border-amber-800/60 dark:text-amber-100">
      <div className="mb-1 font-medium">图片来源</div>
      <div className="space-y-1">
        {images.map((image, index) => (
          <div
            key={`${image.page ?? "page"}-${image.image_index ?? "image"}-${index}`}
            className={`flex min-w-0 flex-wrap gap-x-2 gap-y-1 rounded px-1.5 py-1 ${
              image.low_confidence ? "bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-100" : "bg-amber-50/70 dark:bg-amber-950/30"
            }`}
          >
            <span className="shrink-0 rounded bg-white px-1.5 py-0.5 text-amber-700 dark:bg-gray-900 dark:text-amber-200">
              图片 {typeof image.image_index === "number" ? image.image_index : index + 1}
            </span>
            <span className="min-w-0 break-all">{formatOcrImageRef(image, index)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatChunkArtifactQualityWarnings(chunk: DocumentChunkPreview) {
  const quality = chunk.artifact_quality;
  if (!quality || quality.status !== "warn" || !quality.warnings?.length) return "";
  return quality.warnings.join(" · ");
}

function ChunkArtifactPreview({ chunk }: { chunk: DocumentChunkPreview }) {
  const artifact = chunk.artifact;
  if (!artifact) return null;

  if (artifact.type === "table") {
    const headers = artifact.headers || [];
    const rows = artifact.rows || [];
    const sources = artifact.sources || [];
    const sourceLocator = <TableSourceLocator sources={sources} />;
    if (headers.length > 0 && rows.length > 0) {
      return (
        <div className="mt-3">
          <div className="overflow-x-auto rounded border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-950">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                <tr>
                  {headers.map((header) => (
                    <th key={header || "empty-column"} className="whitespace-nowrap px-2 py-1.5 font-medium">
                      {header || "未命名列"}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {rows.map((row) => (
                  <tr key={`${chunk.id}-row-${row.join("|")}`}>
                    {headers.map((_, colIndex) => (
                      <td key={`${chunk.id}-cell-${headers[colIndex] || row[colIndex] || "empty"}`} className="max-w-[220px] truncate px-2 py-1.5 text-gray-700 dark:text-gray-200">
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
        <div className="mt-3">
          <pre className="overflow-x-auto rounded border border-gray-200 bg-white p-2 text-xs text-gray-700 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200">
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
      <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-2 text-xs leading-5 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
        <div className="whitespace-pre-wrap break-words">{artifact.text || chunk.preview}</div>
        <OcrSourceLocator images={images} />
      </div>
    );
  }

  return null;
}

export default function DocumentsPage() {
  const [loading, setLoading] = useState(true);
  const [loadingStep, setLoadingStep] = useState(0);
  const [error, setError] = useState<string>("");

  const [knowledgeSpaces, setKnowledgeSpaces] = useState<KnowledgeSpace[]>([]);
  const [selectedKnowledgeSpaceId, setSelectedKnowledgeSpaceId] = useState<string | undefined>(undefined);
  const [creatingSpace, setCreatingSpace] = useState(false);
  const [newSpaceName, setNewSpaceName] = useState("");
  const [newSpaceDesc, setNewSpaceDesc] = useState("");

  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [pageSize] = useState(20);
  const [chunkPanelDoc, setChunkPanelDoc] = useState<Document | null>(null);
  const [chunkPreview, setChunkPreview] = useState<DocumentChunkPreview[]>([]);
  const [chunkPreviewTotal, setChunkPreviewTotal] = useState(0);
  const [chunkPreviewAllTotal, setChunkPreviewAllTotal] = useState(0);
  const [chunkPreviewFilter, setChunkPreviewFilter] = useState("all");
  const [chunkPreviewFeature, setChunkPreviewFeature] = useState("all");
  const [chunkPreviewQuery, setChunkPreviewQuery] = useState("");
  const [chunkPreviewAppliedQuery, setChunkPreviewAppliedQuery] = useState("");
  const [chunkPreviewLoading, setChunkPreviewLoading] = useState(false);
  const [chunkPreviewLoadingMore, setChunkPreviewLoadingMore] = useState(false);
  const [chunkPreviewError, setChunkPreviewError] = useState("");
  const [chunkPanelQuality, setChunkPanelQuality] = useState<ParseQualitySummary | null>(null);
  const [highlightedChunkTarget, setHighlightedChunkTarget] = useState<ChunkDeepLinkTarget | null>(null);

  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const processedChunkDeepLinkRef = useRef<string | null>(null);
  const highlightedChunkRef = useRef<HTMLDivElement | null>(null);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [refreshIntervalMs, setRefreshIntervalMs] = useState(3000);
  const [toast, setToast] = useState<{ isOpen: boolean; message: string; type: ToastType }>({
    isOpen: false,
    message: "",
    type: "info",
  });

  const loadingSteps = ["正在加载知识空间列表...", "正在加载文档列表...", "准备就绪"];

  const showToast = useCallback((message: string, type: ToastType) => {
    setToast({ isOpen: true, message, type });
  }, []);

  const loadKnowledgeSpaces = useCallback(async () => {
    const result = await apiClient.listKnowledgeSpaces();
    if (result.error) throw new Error(result.error);
    const list = result.data?.knowledge_spaces || [];
    setKnowledgeSpaces(list);
    const defaultSpace = list.find((s) => s.is_default);
    setSelectedKnowledgeSpaceId((prev) => prev || defaultSpace?.id || list[0]?.id);
  }, []);

  const loadDocuments = useCallback(
    async (knowledgeSpaceId?: string, nextPage: number = page) => {
      const skip = nextPage * pageSize;
      const result = await apiClient.listDocuments(knowledgeSpaceId, skip, pageSize);
      if (result.error) throw new Error(result.error);
      setDocuments(result.data?.documents || []);
      setTotal(result.data?.total || 0);
    },
    [page, pageSize]
  );

  const hasProcessingDocs = useMemo(
    () => documents.some((d) => d.status && ["uploading", "processing", "parsing", "chunking", "embedding"].includes(d.status)),
    [documents]
  );

  const chunkFilterOptions = useMemo(
    () => getChunkFilterOptions(chunkPanelQuality),
    [chunkPanelQuality],
  );
  const chunkFeatureFilterOptions = useMemo(
    () => getChunkFeatureFilterOptions(chunkPanelQuality),
    [chunkPanelQuality],
  );
  const qualityIssueChips = useMemo<QualityIssueChip[]>(() => {
    if (!chunkPanelQuality) return [];
    return [
      { feature: "artifact_issue", label: "Artifact问题", count: chunkPanelQuality.artifact_issue_count },
      { feature: "table_missing_structure", label: "表格缺结构", count: chunkPanelQuality.table_artifact_missing_structure_count },
      { feature: "table_missing_source", label: "表格缺来源", count: chunkPanelQuality.table_artifact_missing_source_count },
      { feature: "ocr_missing_source", label: "OCR缺来源", count: chunkPanelQuality.ocr_artifact_missing_source_count },
      { feature: "ocr_low_confidence", label: "OCR低置信", count: chunkPanelQuality.ocr_artifact_low_confidence_source_count },
    ].filter((item): item is QualityIssueChip => typeof item.count === "number" && item.count > 0);
  }, [chunkPanelQuality]);
  const chunkPreviewHasMore = chunkPreview.length < chunkPreviewTotal;

  useEffect(() => {
    let mounted = true;
    const init = async () => {
      try {
        setLoading(true);
        setLoadingStep(0);
        await loadKnowledgeSpaces();
        if (!mounted) return;

        setLoadingStep(1);
        await loadDocuments(undefined, 0);
        if (!mounted) return;

        setLoadingStep(2);
        setLoading(false);
      } catch (e) {
        if (!mounted) return;
        setError((e as Error).message || "初始化失败");
        setLoading(false);
      }
    };
    init();
    return () => {
      mounted = false;
      if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    };
  }, [loadKnowledgeSpaces, loadDocuments]);

  useEffect(() => {
    if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
    pollingTimerRef.current = null;

    if (!autoRefreshEnabled) return;
    if (refreshIntervalMs <= 0) return;
    // 默认仍然只在存在处理中文档时自动刷新，避免空转刷接口
    if (!hasProcessingDocs) return;

    pollingTimerRef.current = setInterval(() => {
      loadDocuments(selectedKnowledgeSpaceId, page).catch(() => {});
    }, refreshIntervalMs);

    return () => {
      if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    };
  }, [autoRefreshEnabled, hasProcessingDocs, loadDocuments, page, refreshIntervalMs, selectedKnowledgeSpaceId]);

  const handleRefresh = async () => {
    try {
      await loadDocuments(selectedKnowledgeSpaceId, page);
      showToast("已刷新", "success");
    } catch (e) {
      showToast((e as Error).message || "刷新失败", "error");
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm("确认删除该文档及其向量数据？")) return;
    const result = await apiClient.deleteDocument(docId);
    if (result.error) {
      showToast(result.error, "error");
      return;
    }
    showToast("已删除", "success");
    await loadDocuments(selectedKnowledgeSpaceId, page);
  };

  const loadChunkPreview = useCallback(
    async (
      doc: Document,
      filter: string,
      feature: string,
      query: string,
      options?: {
        skip?: number;
        append?: boolean;
        targetChunkId?: string;
        targetChunkIndex?: number;
        contextWindow?: number;
      },
    ) => {
      const append = options?.append ?? false;
      const skip = options?.skip ?? 0;
      setChunkPanelDoc(doc);
      setChunkPreviewError("");
      if (append) {
        setChunkPreviewLoadingMore(true);
      } else {
        setChunkPreview([]);
        setChunkPreviewTotal(0);
        setChunkPreviewAllTotal(0);
        setChunkPanelQuality(doc.parse_quality || null);
        setChunkPreviewLoading(true);
      }
      try {
        const result = await apiClient.getDocumentChunks(doc.id, {
          skip,
          limit: 80,
          includeText: false,
          contentType: filter,
          feature,
          query,
          targetChunkId: options?.targetChunkId,
          targetChunkIndex: options?.targetChunkIndex,
          contextWindow: options?.contextWindow,
        });
        if (result.error) throw new Error(result.error);
        const nextChunks = result.data?.chunks || [];
        setChunkPreview((prev) => (append ? [...prev, ...nextChunks] : nextChunks));
        setChunkPreviewTotal(result.data?.total_chunks || 0);
        setChunkPreviewAllTotal(result.data?.total_all_chunks ?? result.data?.total_chunks ?? 0);
        setChunkPanelQuality(
          result.data?.parse_quality ||
            doc.parse_quality ||
            ((result.data?.chunks?.[0]?.parse_summary as ParseQualitySummary | undefined) ?? null),
        );
        if (options?.targetChunkId || typeof options?.targetChunkIndex === "number") {
          if (result.data?.target_found === false) {
            setHighlightedChunkTarget(null);
            highlightedChunkRef.current = null;
            showToast("未在当前切块结果中找到目标证据", "warning");
          } else {
            setHighlightedChunkTarget({
              documentId: doc.id,
              chunkId: result.data?.target_chunk_id || options.targetChunkId,
              chunkIndex:
                typeof result.data?.target_chunk_index === "number"
                  ? result.data.target_chunk_index
                  : options.targetChunkIndex,
            });
          }
        }
      } catch (e) {
        setChunkPreviewError((e as Error).message || "加载切块失败");
      } finally {
        if (append) {
          setChunkPreviewLoadingMore(false);
        } else {
          setChunkPreviewLoading(false);
        }
      }
    },
    [showToast],
  );

  const handleViewChunks = async (doc: Document) => {
    setChunkPreviewFilter("all");
    setChunkPreviewFeature("all");
    setChunkPreviewQuery("");
    setChunkPreviewAppliedQuery("");
    setHighlightedChunkTarget(null);
    highlightedChunkRef.current = null;
    await loadChunkPreview(doc, "all", "all", "");
  };

  const handleChunkFilterChange = async (filter: string) => {
    if (!chunkPanelDoc || filter === chunkPreviewFilter) return;
    setChunkPreviewFilter(filter);
    setHighlightedChunkTarget(null);
    highlightedChunkRef.current = null;
    await loadChunkPreview(chunkPanelDoc, filter, chunkPreviewFeature, chunkPreviewAppliedQuery);
  };

  const handleChunkFeatureChange = async (feature: string) => {
    if (!chunkPanelDoc || feature === chunkPreviewFeature) return;
    setChunkPreviewFeature(feature);
    setHighlightedChunkTarget(null);
    highlightedChunkRef.current = null;
    await loadChunkPreview(chunkPanelDoc, chunkPreviewFilter, feature, chunkPreviewAppliedQuery);
  };

  const handleQualityCheckFilter = async (check: ParseQualityCheckItem) => {
    if (!chunkPanelDoc) return;
    const nextFilter = check.content_type_filter || "all";
    const nextFeature = check.feature_filter || "all";
    if (nextFilter === "all" && nextFeature === "all") return;
    setChunkPreviewFilter(nextFilter);
    setChunkPreviewFeature(nextFeature);
    setChunkPreviewQuery("");
    setChunkPreviewAppliedQuery("");
    setHighlightedChunkTarget(null);
    highlightedChunkRef.current = null;
    await loadChunkPreview(chunkPanelDoc, nextFilter, nextFeature, "");
  };

  const handleQualityFeatureFilter = async (feature: string) => {
    if (!chunkPanelDoc || feature === "all") return;
    setChunkPreviewFilter("all");
    setChunkPreviewFeature(feature);
    setChunkPreviewQuery("");
    setChunkPreviewAppliedQuery("");
    setHighlightedChunkTarget(null);
    highlightedChunkRef.current = null;
    await loadChunkPreview(chunkPanelDoc, "all", feature, "");
  };

  const handleChunkSearch = async () => {
    if (!chunkPanelDoc) return;
    const nextQuery = chunkPreviewQuery.trim();
    setChunkPreviewAppliedQuery(nextQuery);
    setHighlightedChunkTarget(null);
    highlightedChunkRef.current = null;
    await loadChunkPreview(chunkPanelDoc, chunkPreviewFilter, chunkPreviewFeature, nextQuery);
  };

  const handleClearChunkSearch = async () => {
    if (!chunkPanelDoc) return;
    setChunkPreviewQuery("");
    setChunkPreviewAppliedQuery("");
    setHighlightedChunkTarget(null);
    highlightedChunkRef.current = null;
    await loadChunkPreview(chunkPanelDoc, chunkPreviewFilter, chunkPreviewFeature, "");
  };

  const handleLoadMoreChunks = async () => {
    if (!chunkPanelDoc || chunkPreviewLoading || chunkPreviewLoadingMore || !chunkPreviewHasMore) return;
    await loadChunkPreview(chunkPanelDoc, chunkPreviewFilter, chunkPreviewFeature, chunkPreviewAppliedQuery, {
      skip: chunkPreview.length,
      append: true,
    });
  };

  useEffect(() => {
    if (loading || error) return;
    const target = parseChunkDeepLinkTarget();
    if (!target) return;

    const key = chunkTargetKey(target);
    if (processedChunkDeepLinkRef.current === key) return;
    processedChunkDeepLinkRef.current = key;

    const openTargetChunk = async () => {
      let targetDoc = documents.find((doc) => doc.id === target.documentId);
      if (!targetDoc) {
        const detail = await apiClient.getDocumentDetail(target.documentId);
        if (detail.error || !detail.data) throw new Error(detail.error || "文档不存在");
        targetDoc = documentFromDetail(detail.data);
      }

      const nextFilter = target.contentType || "all";
      const nextFeature = target.feature || "all";
      setChunkPreviewFilter(nextFilter);
      setChunkPreviewFeature(nextFeature);
      setChunkPreviewQuery("");
      setChunkPreviewAppliedQuery("");
      setHighlightedChunkTarget(target);
      highlightedChunkRef.current = null;
      await loadChunkPreview(targetDoc, nextFilter, nextFeature, "", {
        targetChunkId: target.chunkId,
        targetChunkIndex: target.chunkIndex,
        contextWindow: 6,
      });
    };

    openTargetChunk().catch((e) => {
      showToast((e as Error).message || "定位证据切块失败", "error");
    });
  }, [documents, error, loading, loadChunkPreview, showToast]);

  useEffect(() => {
    if (!highlightedChunkTarget || chunkPreviewLoading || chunkPreview.length === 0) return;
    window.setTimeout(() => {
      highlightedChunkRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 50);
  }, [chunkPreview.length, chunkPreviewLoading, highlightedChunkTarget]);

  const handleCreateSpace = async () => {
    const name = newSpaceName.trim();
    if (!name) {
      showToast("知识空间名称不能为空", "warning");
      return;
    }
    setCreatingSpace(true);
    try {
      const result = await apiClient.createKnowledgeSpace({
        name,
        description: newSpaceDesc.trim() || undefined,
      });
      if (result.error) throw new Error(result.error);
      showToast("已创建知识空间", "success");
      setNewSpaceName("");
      setNewSpaceDesc("");
      await loadKnowledgeSpaces();
    } catch (e) {
      showToast((e as Error).message || "创建失败", "error");
    } finally {
      setCreatingSpace(false);
    }
  };

  if (loading) {
    return (
      <Layout allowScroll>
        <div className="flex min-h-[40vh] items-center justify-center">
          <LoadingProgress steps={loadingSteps} currentStep={loadingStep} className="min-h-[40vh]" />
        </div>
      </Layout>
    );
  }

  return (
    <Layout allowScroll>
      <div className="w-full max-w-full space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="text-xl font-bold text-gray-900 dark:text-gray-100">知识库</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">上传文档入库后，可在聊天中开启“知识库检索”进行RAG检索增强。</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              type="button"
              className="px-3 py-2 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700"
            >
              刷新
            </button>
            <div className="hidden sm:flex items-center gap-2 pl-2">
              <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300 select-none">
                <input
                  type="checkbox"
                  checked={autoRefreshEnabled}
                  onChange={(e) => setAutoRefreshEnabled(e.target.checked)}
                />
                自动刷新
              </label>
              <select
                value={String(refreshIntervalMs)}
                onChange={(e) => setRefreshIntervalMs(Number(e.target.value))}
                className="px-2 py-2 rounded-lg text-xs border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
                title="自动刷新周期（仅在有处理中文档时生效）"
              >
                <option value="2000">2s</option>
                <option value="3000">3s</option>
                <option value="5000">5s</option>
                <option value="10000">10s</option>
                <option value="30000">30s</option>
              </select>
            </div>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800">
            {error}
          </div>
        )}

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600 dark:text-gray-300 whitespace-nowrap">知识空间</span>
            <select
              value={selectedKnowledgeSpaceId || ""}
              onChange={(e) => {
                const v = e.target.value || undefined;
                setSelectedKnowledgeSpaceId(v);
                setPage(0);
                loadDocuments(v, 0).catch(() => {});
              }}
              className="px-3 py-2 rounded-lg text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
            >
              {knowledgeSpaces.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.is_default ? "（默认）" : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1" />
          <button
            onClick={handleCreateSpace}
            disabled={creatingSpace}
            type="button"
            className="px-3 py-2 rounded-lg text-sm bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
          >
            新增知识空间
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-stretch">
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 min-w-0 flex flex-col">
            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-3">创建知识空间</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 flex-1">
              <input
                value={newSpaceName}
                onChange={(e) => setNewSpaceName(e.target.value)}
                placeholder="知识空间名称（必填）"
                className="min-w-0 px-3 py-2 rounded-lg text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
              />
              <input
                value={newSpaceDesc}
                onChange={(e) => setNewSpaceDesc(e.target.value)}
                placeholder="描述（可选）"
                className="min-w-0 px-3 py-2 rounded-lg text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
              />
              <button
                onClick={handleCreateSpace}
                disabled={creatingSpace}
                type="button"
                className="px-3 py-2 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-60 sm:col-span-2 w-full sm:w-auto sm:justify-self-start"
              >
                {creatingSpace ? "创建中..." : "创建"}
              </button>
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">
              上传文档/对话附件前需要先选择目标知识空间。
            </div>
          </div>

          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 min-w-0 flex flex-col">
            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-3">上传入库</div>
            <div className="flex-1 min-h-0">
              <DocumentUpload
                knowledgeSpaceId={selectedKnowledgeSpaceId}
                onUploadSuccess={async () => {
                  showToast("上传成功，正在后台处理", "success");
                  await loadDocuments(selectedKnowledgeSpaceId, page);
                }}
              />
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-dashed border-gray-200 dark:border-gray-600 bg-gray-50/50 dark:bg-gray-800/20 px-3 py-2 text-xs text-gray-600 dark:text-gray-400">
          图谱、重排、OCR、向量化并发等全局运行时选项已移至导航中的「
          <Link href="/settings" className="text-blue-600 dark:text-blue-400 hover:underline font-medium">
            高级配置
          </Link>
          」。
        </div>

        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden w-full">
          <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">
              文档列表 <span className="text-gray-500 dark:text-gray-400 font-normal">({total})</span>
            </div>
          </div>

          <div className="divide-y divide-gray-100 dark:divide-gray-800">
            {documents.length === 0 ? (
              <div className="p-6 text-sm text-gray-500 dark:text-gray-400">暂无文档</div>
            ) : (
              documents.map((d) => (
                <div key={d.id} className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-medium text-gray-900 dark:text-gray-100 truncate">{d.title}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {d.file_type} · {(d.file_size / 1024 / 1024).toFixed(2)} MB · {formatDateTime(d.created_at)}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      状态：{d.status || "unknown"}
                      {typeof d.progress_percentage === "number" ? `（${d.progress_percentage}%）` : ""}
                      {d.current_stage ? ` · ${d.current_stage}` : ""}
                    </div>
                    {d.parse_quality && (
                      <div className="mt-1 text-xs text-blue-700 dark:text-blue-300">
                        {formatParseQualityLine(d.parse_quality)}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleViewChunks(d)}
                      type="button"
                      className="px-3 py-2 rounded-lg text-sm bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/30"
                    >
                      切块
                    </button>
                    <button
                      onClick={() => handleDelete(d.id)}
                      type="button"
                      className="px-3 py-2 rounded-lg text-sm bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/30"
                    >
                      删除
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between text-sm">
            <div className="text-gray-500 dark:text-gray-400">
              第 {page + 1} 页 / 共 {Math.max(1, Math.ceil(total / pageSize))} 页
            </div>
            <div className="flex gap-2">
              <button
                disabled={page === 0}
                type="button"
                onClick={() => {
                  const p = Math.max(0, page - 1);
                  setPage(p);
                  loadDocuments(selectedKnowledgeSpaceId, p).catch(() => {});
                }}
                className="px-3 py-2 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 disabled:opacity-50"
              >
                上一页
              </button>
              <button
                disabled={(page + 1) * pageSize >= total}
                type="button"
                onClick={() => {
                  const p = page + 1;
                  setPage(p);
                  loadDocuments(selectedKnowledgeSpaceId, p).catch(() => {});
                }}
                className="px-3 py-2 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 disabled:opacity-50"
              >
                下一页
              </button>
            </div>
          </div>
        </div>
      </div>

      {chunkPanelDoc && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" role="dialog" aria-modal="true">
          <div className="h-full w-full max-w-3xl overflow-hidden bg-white shadow-2xl dark:bg-gray-950">
            <div className="flex items-start justify-between gap-3 border-b border-gray-200 px-5 py-4 dark:border-gray-800">
              <div className="min-w-0">
                <div className="truncate text-base font-semibold text-gray-900 dark:text-gray-100">{chunkPanelDoc.title}</div>
                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {chunkPanelDoc.file_type} · {chunkPreviewTotal} / {chunkPreviewAllTotal || chunkPreviewTotal} 个 chunk
                </div>
              </div>
              <button
                className="rounded-lg bg-gray-100 px-3 py-2 text-sm text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                type="button"
                onClick={() => {
                  setChunkPanelDoc(null);
                  setChunkPreview([]);
                  setChunkPreviewTotal(0);
                  setChunkPreviewAllTotal(0);
                  setChunkPreviewFilter("all");
                  setChunkPreviewQuery("");
                  setChunkPreviewAppliedQuery("");
                  setChunkPreviewLoadingMore(false);
                  setChunkPreviewError("");
                  setChunkPanelQuality(null);
                  setHighlightedChunkTarget(null);
                  highlightedChunkRef.current = null;
                }}
              >
                关闭
              </button>
            </div>

            <div className="h-[calc(100%-73px)] overflow-y-auto p-5">
              {chunkPanelQuality && (
                <div className="mb-4 rounded-lg border border-blue-100 bg-blue-50 p-4 dark:border-blue-900/50 dark:bg-blue-950/30">
                  <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                    <div>
                      <div className="text-gray-500 dark:text-gray-400">解析质量</div>
                      <div className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                        {typeof chunkPanelQuality.quality_score === "number" ? `${chunkPanelQuality.quality_score}` : "-"}
                      </div>
                      {chunkPanelQuality.risk_level && (
                        <div className={`mt-1 inline-flex rounded px-2 py-0.5 text-[11px] font-medium ${parseRiskClass(chunkPanelQuality.risk_level)}`}>
                          {parseRiskLabel(chunkPanelQuality.risk_level)}
                        </div>
                      )}
                    </div>
                    <div>
                      <div className="text-gray-500 dark:text-gray-400">页面覆盖</div>
                      <div className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                        {formatPercent(chunkPanelQuality.page_coverage)}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500 dark:text-gray-400">表格 / 公式</div>
                      <div className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                        {chunkPanelQuality.table_count ?? 0} / {chunkPanelQuality.formula_count ?? 0}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500 dark:text-gray-400">图片 / OCR</div>
                      <div className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                        {chunkPanelQuality.image_count ?? 0} / {chunkPanelQuality.ocr_text_length ?? 0}
                      </div>
                      {(typeof chunkPanelQuality.ocr_image_coverage === "number" || typeof chunkPanelQuality.ocr_avg_confidence === "number") && (
                        <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                          {typeof chunkPanelQuality.ocr_image_coverage === "number" && (
                            <span>覆盖 {formatPercent(chunkPanelQuality.ocr_image_coverage)}</span>
                          )}
                          {typeof chunkPanelQuality.ocr_image_coverage === "number" && typeof chunkPanelQuality.ocr_avg_confidence === "number" && (
                            <span> · </span>
                          )}
                          {typeof chunkPanelQuality.ocr_avg_confidence === "number" && (
                            <span>置信度 {formatPercent(chunkPanelQuality.ocr_avg_confidence)}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs">
                    {chunkPanelQuality.parser_type && (
                      <span className="rounded bg-white px-2 py-1 text-gray-700 dark:bg-gray-900 dark:text-gray-200">
                        {chunkPanelQuality.parser_type}
                      </span>
                    )}
                    {chunkPanelQuality.extraction_method && (
                      <span className="rounded bg-white px-2 py-1 text-gray-700 dark:bg-gray-900 dark:text-gray-200">
                        {chunkPanelQuality.extraction_method}
                      </span>
                    )}
                    {Object.entries(chunkPanelQuality.content_type_counts || {}).map(([type, count]) => (
                      <span key={type} className="rounded bg-white px-2 py-1 text-gray-700 dark:bg-gray-900 dark:text-gray-200">
                        {contentTypeLabel[type] || type} {count}
                      </span>
                    ))}
                    {typeof chunkPanelQuality.chunk_anchor_coverage === "number" && (
                      <span className="rounded bg-white px-2 py-1 text-gray-700 dark:bg-gray-900 dark:text-gray-200">
                        定位 {formatPercent(chunkPanelQuality.chunk_anchor_coverage)}
                      </span>
                    )}
                    {typeof chunkPanelQuality.chunk_token_avg === "number" && (
                      <span className="rounded bg-white px-2 py-1 text-gray-700 dark:bg-gray-900 dark:text-gray-200">
                        平均 {chunkPanelQuality.chunk_token_avg} tokens
                      </span>
                    )}
                    {typeof chunkPanelQuality.chunk_short_count === "number" && chunkPanelQuality.chunk_short_count > 0 && (
                      <span className="rounded bg-white px-2 py-1 text-amber-700 dark:bg-gray-900 dark:text-amber-200">
                        过短 {chunkPanelQuality.chunk_short_count}
                      </span>
                    )}
                    {typeof chunkPanelQuality.chunk_large_count === "number" && chunkPanelQuality.chunk_large_count > 0 && (
                      <span className="rounded bg-white px-2 py-1 text-amber-700 dark:bg-gray-900 dark:text-amber-200">
                        过长 {chunkPanelQuality.chunk_large_count}
                      </span>
                    )}
                    {qualityIssueChips.map((chip) => (
                      <button
                        key={chip.feature}
                        type="button"
                        disabled={chunkPreviewLoading}
                        onClick={() => handleQualityFeatureFilter(chip.feature).catch(() => {})}
                        className="rounded bg-white px-2 py-1 text-left text-amber-700 hover:bg-amber-50 disabled:opacity-60 dark:bg-gray-900 dark:text-amber-200 dark:hover:bg-gray-800"
                        title={`筛选${chip.label}切块`}
                      >
                        {chip.label} {chip.count}
                      </button>
                    ))}
                  </div>
                  {chunkPanelQuality.warnings && chunkPanelQuality.warnings.length > 0 && (
                    <div className="mt-3 text-xs text-amber-700 dark:text-amber-300">
                      {chunkPanelQuality.warnings.join("；")}
                    </div>
                  )}
                  {chunkPanelQuality.quality_checks && chunkPanelQuality.quality_checks.length > 0 && (
                    <div className="mt-3 grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                      {chunkPanelQuality.quality_checks.map((check) => (
                        <div key={check.id} className={`border-l-2 py-1.5 pl-2 text-xs ${parseCheckClass(check.status)}`}>
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-medium">{check.label}</span>
                            <span>{parseCheckStatusLabel(check.status)}</span>
                          </div>
                          <div className="mt-1 leading-5">{check.message}</div>
                          {check.action && check.status !== "pass" && (
                            <div className="mt-1 opacity-80">{check.action}</div>
                          )}
                          {check.status !== "pass" && (check.content_type_filter || check.feature_filter) && (
                            <button
                              type="button"
                              disabled={chunkPreviewLoading}
                              onClick={() => handleQualityCheckFilter(check).catch(() => {})}
                              className="mt-2 rounded bg-white px-2 py-1 text-[11px] font-medium text-gray-700 shadow-sm ring-1 ring-inset ring-gray-200 hover:bg-gray-50 disabled:opacity-60 dark:bg-gray-900 dark:text-gray-100 dark:ring-gray-700 dark:hover:bg-gray-800"
                            >
                              {check.filter_label || "查看相关切块"}
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {chunkPanelQuality.recommendations && chunkPanelQuality.recommendations.length > 0 && (
                    <div className="mt-3 border-t border-amber-200 pt-2 text-xs text-amber-800 dark:border-amber-900/60 dark:text-amber-100">
                      <div className="font-medium">建议动作</div>
                      <ul className="mt-1 list-disc space-y-1 pl-4">
                        {chunkPanelQuality.recommendations.slice(0, 4).map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              <div className="mb-3 flex flex-col gap-2 sm:flex-row">
                <input
                  value={chunkPreviewQuery}
                  onChange={(event) => setChunkPreviewQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      handleChunkSearch().catch(() => {});
                    }
                  }}
                  placeholder="搜索 chunk 内容、章节、表格或 OCR 文本"
                  className="min-w-0 flex-1 rounded border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={chunkPreviewLoading}
                    onClick={() => handleChunkSearch().catch(() => {})}
                    className="rounded bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-60"
                  >
                    搜索
                  </button>
                  {chunkPreviewAppliedQuery && (
                    <button
                      type="button"
                      disabled={chunkPreviewLoading}
                      onClick={() => handleClearChunkSearch().catch(() => {})}
                      className="rounded bg-gray-100 px-3 py-2 text-sm text-gray-700 hover:bg-gray-200 disabled:opacity-60 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                    >
                      清空
                    </button>
                  )}
                </div>
              </div>

              {chunkPreviewAppliedQuery && (
                <div className="mb-3 text-xs text-gray-500 dark:text-gray-400">
                  关键词：{chunkPreviewAppliedQuery}
                </div>
              )}

              <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
                {chunkFilterOptions.map((option) => {
                  const active = option.value === chunkPreviewFilter;
                  const count = option.value === "all" ? chunkPreviewAllTotal || chunkPreviewTotal : option.count;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      disabled={chunkPreviewLoading}
                      onClick={() => handleChunkFilterChange(option.value)}
                      className={`rounded border px-2.5 py-1.5 transition-colors disabled:opacity-60 ${
                        active
                          ? "border-gray-900 bg-gray-900 text-white dark:border-gray-100 dark:bg-gray-100 dark:text-gray-900"
                          : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
                      }`}
                    >
                      {option.label}
                      {typeof count === "number" && count > 0 ? ` ${count}` : ""}
                    </button>
                  );
                })}
              </div>

              <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
                <span className="text-gray-500 dark:text-gray-400">质量筛选</span>
                {chunkFeatureFilterOptions.map((option) => {
                  const active = option.value === chunkPreviewFeature;
                  const count = option.count;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      disabled={chunkPreviewLoading}
                      onClick={() => handleChunkFeatureChange(option.value)}
                      className={`rounded border px-2.5 py-1.5 transition-colors disabled:opacity-60 ${
                        active
                          ? "border-amber-700 bg-amber-700 text-white dark:border-amber-200 dark:bg-amber-200 dark:text-amber-950"
                          : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
                      }`}
                    >
                      {option.label}
                      {typeof count === "number" && count > 0 ? ` ${count}` : ""}
                    </button>
                  );
                })}
              </div>

              {chunkPreviewLoading && (
                <div className="rounded-lg border border-gray-200 p-4 text-sm text-gray-500 dark:border-gray-800 dark:text-gray-400">
                  加载中...
                </div>
              )}

              {chunkPreviewError && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                  {chunkPreviewError}
                </div>
              )}

              {!chunkPreviewLoading && !chunkPreviewError && chunkPreview.length === 0 && (
                <div className="rounded-lg border border-gray-200 p-4 text-sm text-gray-500 dark:border-gray-800 dark:text-gray-400">
                  暂无切块数据
                </div>
              )}

              <div className="space-y-3">
                {chunkPreview.map((chunk) => {
                  const typeLabel = contentTypeLabel[chunk.content_type] || chunk.content_type || "文本";
                  const featureFlags = Object.entries(chunk.features || {})
                    .filter(([, enabled]) => enabled)
                    .map(([key]) => {
                      const value = key.replace(/^has_/, "");
                      return { key, label: featureFlagLabel[value] || value };
                    });
                  const highlighted = isHighlightedChunk(chunk, highlightedChunkTarget);
                  return (
                    <div
                      key={chunk.id || `${chunk.chunk_index}`}
                      ref={(node) => {
                        if (highlighted) highlightedChunkRef.current = node;
                      }}
                      className={`rounded-lg border p-4 transition-colors ${
                        highlighted
                          ? "border-amber-400 bg-amber-50 ring-2 ring-amber-300 dark:border-amber-500 dark:bg-amber-950/30 dark:ring-amber-700"
                          : "border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900"
                      }`}
                    >
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="rounded bg-gray-900 px-2 py-1 font-medium text-white dark:bg-gray-100 dark:text-gray-900">
                          #{typeof chunk.chunk_index === "number" ? chunk.chunk_index + 1 : "-"}
                        </span>
                        <span className="rounded bg-blue-100 px-2 py-1 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200">
                          {typeLabel}
                        </span>
                        {typeof chunk.token_count === "number" && (
                          <span className="rounded bg-gray-100 px-2 py-1 text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                            {chunk.token_count} tokens
                          </span>
                        )}
                        {featureFlags.map((flag) => (
                          <span key={flag.key} className="rounded bg-amber-100 px-2 py-1 text-amber-700 dark:bg-amber-900/30 dark:text-amber-200">
                            {flag.label}
                          </span>
                        ))}
                      </div>
                      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">{formatChunkLocation(chunk)}</div>
                      <div className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-gray-800 dark:text-gray-100">
                        {chunk.preview}
                      </div>
                      {formatChunkArtifactQualityWarnings(chunk) && (
                        <div className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-100">
                          {formatChunkArtifactQualityWarnings(chunk)}
                        </div>
                      )}
                      <ChunkArtifactPreview chunk={chunk} />
                    </div>
                  );
                })}
              </div>

              {!chunkPreviewLoading && !chunkPreviewError && chunkPreview.length > 0 && (
                <div className="mt-4 flex flex-col gap-2 border-t border-gray-200 pt-4 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400 sm:flex-row sm:items-center sm:justify-between">
                  <span>
                    已显示 {chunkPreview.length} / {chunkPreviewTotal} 个匹配 chunk
                  </span>
                  {chunkPreviewHasMore && (
                    <button
                      type="button"
                      disabled={chunkPreviewLoadingMore}
                      onClick={() => handleLoadMoreChunks().catch(() => {})}
                      className="rounded bg-gray-100 px-3 py-2 text-sm text-gray-700 hover:bg-gray-200 disabled:opacity-60 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                    >
                      {chunkPreviewLoadingMore ? "加载中..." : "加载更多"}
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <Toast
        isOpen={toast.isOpen}
        message={toast.message}
        type={toast.type}
        duration={4000}
        onClose={() => setToast((t) => ({ ...t, isOpen: false }))}
      />
    </Layout>
  );
}

