"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DocumentUpload from "@/components/document/DocumentUpload";
import Layout from "@/components/ui/Layout";
import LoadingProgress from "@/components/ui/LoadingProgress";
import Toast, { type ToastType } from "@/components/ui/Toast";
import type { KnowledgeSpace } from "@/lib/api";
import { apiClient, type Document, type DocumentChunkPreview } from "@/lib/api";
import { formatDateTime } from "@/lib/timezone";

const contentTypeLabel: Record<string, string> = {
  text: "文本",
  table: "表格",
  image_ocr: "图片OCR",
  ocr: "OCR",
  formula: "公式",
  code: "代码",
};

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
  const [chunkPreviewLoading, setChunkPreviewLoading] = useState(false);
  const [chunkPreviewError, setChunkPreviewError] = useState("");

  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [refreshIntervalMs, setRefreshIntervalMs] = useState(3000);
  const [toast, setToast] = useState<{ isOpen: boolean; message: string; type: ToastType }>({
    isOpen: false,
    message: "",
    type: "info",
  });

  const loadingSteps = ["正在加载知识空间列表...", "正在加载文档列表...", "准备就绪"];

  const showToast = (message: string, type: ToastType) => setToast({ isOpen: true, message, type });

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

  const handleViewChunks = async (doc: Document) => {
    setChunkPanelDoc(doc);
    setChunkPreview([]);
    setChunkPreviewTotal(0);
    setChunkPreviewError("");
    setChunkPreviewLoading(true);
    try {
      const result = await apiClient.getDocumentChunks(doc.id, {
        limit: 80,
        includeText: false,
      });
      if (result.error) throw new Error(result.error);
      setChunkPreview(result.data?.chunks || []);
      setChunkPreviewTotal(result.data?.total_chunks || 0);
    } catch (e) {
      setChunkPreviewError((e as Error).message || "加载切块失败");
    } finally {
      setChunkPreviewLoading(false);
    }
  };

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
                  {chunkPanelDoc.file_type} · {chunkPreviewTotal} 个 chunk
                </div>
              </div>
              <button
                className="rounded-lg bg-gray-100 px-3 py-2 text-sm text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                type="button"
                onClick={() => {
                  setChunkPanelDoc(null);
                  setChunkPreview([]);
                  setChunkPreviewError("");
                }}
              >
                关闭
              </button>
            </div>

            <div className="h-[calc(100%-73px)] overflow-y-auto p-5">
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
                    .map(([key]) => key.replace(/^has_/, ""));
                  return (
                    <div
                      key={chunk.id || `${chunk.chunk_index}`}
                      className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-900"
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
                          <span key={flag} className="rounded bg-amber-100 px-2 py-1 text-amber-700 dark:bg-amber-900/30 dark:text-amber-200">
                            {flag}
                          </span>
                        ))}
                      </div>
                      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">{formatChunkLocation(chunk)}</div>
                      <div className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-gray-800 dark:text-gray-100">
                        {chunk.preview}
                      </div>
                    </div>
                  );
                })}
              </div>
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

