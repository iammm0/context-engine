"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import ChatMessage from "@/components/chat/ChatMessage";
import ChatSidebar from "@/components/chat/ChatSidebar";
import Layout from "@/components/ui/Layout";
import LoadingProgress from "@/components/ui/LoadingProgress";
import DeepResearchRenderer from "@/components/chat/DeepResearchRenderer";
import AgentStatusPanel from "@/components/chat/AgentStatusPanel";
import Toast from "@/components/ui/Toast";
import { apiClient, Document, Model } from "@/lib/api";
import {
  ChatMessage as MessageType,
  SourceInfo,
  type CitationQuality,
  type EvidenceItem,
  type EvidenceQuality,
  type RAGEvaluationMetrics,
} from "../../types/chat";
import { addConversation } from "@/lib/conversation";
import { Conversation } from "@/types/conversation";
import { formatChatTimestamp } from "@/lib/timezone";
import type { KnowledgeSpace } from "@/lib/api";

export default function ChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<MessageType[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [selectedDocumentId, setSelectedDocumentId] = useState<
    string | undefined
  >();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [knowledgeSpaces, setKnowledgeSpaces] = useState<KnowledgeSpace[]>([]);
  const [selectedKnowledgeSpaceIds, setSelectedKnowledgeSpaceIds] = useState<
    string[]
  >([]);
  const [isLoadingKnowledgeSpaces, setIsLoadingKnowledgeSpaces] =
    useState(false);
  const [spacePickerOpen, setSpacePickerOpen] = useState(false);
  const [spacePickerQuery, setSpacePickerQuery] = useState("");
  const spacePickerRef = useRef<HTMLDivElement>(null);
  const [isInitializing, setIsInitializing] = useState(true);
  const [initStep, setInitStep] = useState(0);
  const [mounted, setMounted] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [copiedConversation, setCopiedConversation] = useState(false);
  // 快捷提示词轮换相关状态
  const [quickPromptsRotationIndex, setQuickPromptsRotationIndex] = useState(0);
  const [displayedQuickPrompts, setDisplayedQuickPrompts] = useState<string[]>(
    [],
  );
  // 流式更新节流相关
  const streamingUpdateTimerRef = useRef<NodeJS.Timeout | null>(null);
  const pendingContentRef = useRef<string>("");
  const isStreamingRef = useRef<boolean>(false);
  // 状态持久化相关
  const getStorageKey = useCallback(() => {
    return `chat_state_${conversationId || "new"}`;
  }, [conversationId]);
  const saveStateTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 流式输出开关（强制开启）
  const useStreaming = true;

  // 模型配置
  const [models, setModels] = useState<Model[]>([]);
  const [selectedLLM, setSelectedLLM] = useState<string>("");
  const [selectedEmbedding, setSelectedEmbedding] = useState<string>("");
  const [showModelSettings, setShowModelSettings] = useState(false);

  // AbortController
  const abortControllerRef = useRef<AbortController | null>(null);

  // 知识库检索增强模式开关（默认关闭）
  const [enableRAG, setEnableRAG] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("enableRAG");
      return saved !== null ? saved === "true" : false; // 默认关闭
    }
    return false;
  });
  // 深度研究功能全局开关（由系统管理员控制）
  const [deepResearchFeatureEnabled, setDeepResearchFeatureEnabled] =
    useState<boolean>(true);

  // 深度研究模式开关（默认关闭）
  const [deepResearchEnabled, setDeepResearchEnabled] = useState<boolean>(
    () => {
      if (typeof window !== "undefined") {
        const saved = localStorage.getItem("deepResearchEnabled");
        return saved !== null ? saved === "true" : false; // 默认关闭
      }
      return false;
    },
  );
  // 深度思考子Agent配置
  const [deepThinkingAgents, setDeepThinkingAgents] = useState<string[]>([]);

  // Agent工作状态（包含更详细的信息）
  const [agentStatuses, setAgentStatuses] = useState<
    Array<{
      agent_type: string;
      status: "pending" | "running" | "completed" | "error" | "skipped";
      progress?: number;
      current_step?: string;
      details?: string;
      started_at?: number;
      completed_at?: number;
      reason?: string; // 用于skipped状态的原因说明
    }>
  >([]);
  // 深度研究模式的Agent结果（markdown格式）
  const [deepResearchResults, setDeepResearchResults] = useState<
    Array<{ agent_type: string; content: string; title?: string }>
  >([]);
  // Toast 提示状态
  const [toast, setToast] = useState<{
    isOpen: boolean;
    message: string;
    type: "success" | "error" | "info" | "warning";
  }>({
    isOpen: false,
    message: "",
    type: "info",
  });
  // 文件上传相关状态
  const [uploadingFile, setUploadingFile] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadedFiles, setUploadedFiles] = useState<
    Array<{
      name: string;
      id: string;
      status: "uploading" | "processing" | "completed" | "failed";
      progress?: number;
      stage?: string;
      stageDetails?: string;
    }>
  >([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const statusPollingRef = useRef<Map<string, NodeJS.Timeout>>(new Map());

  const initSteps = [
    "正在加载知识空间列表...",
    "正在加载文档列表...",
    "准备就绪",
  ];

  // 动态生成加载步骤（基于知识空间）
  const getLoadingSteps = (spaceLabel?: string) => [
    "正在创建对话...",
    "正在保存消息...",
    spaceLabel ? `正在检索：${spaceLabel}...` : "正在检索知识空间...",
    "正在增强上下文...",
    "正在生成回复...",
    "正在保存回复...",
  ];

  // 获取当前步骤的实际进度（基于实际处理时间）
  const getActualProgress = (step: number, totalSteps: number): number => {
    if (totalSteps === 0) return 0;

    // 各步骤的实际耗时权重（基于真实处理时间）
    const stepWeights = [
      0.05, // 步骤0: 创建对话 - 5%
      0.05, // 步骤1: 保存消息 - 5%
      0.15, // 步骤2: 检索知识库 - 15%
      0.05, // 步骤3: 增强上下文 - 5%
      0.6, // 步骤4: 生成回复 - 60%（最耗时）
      0.1, // 步骤5: 保存回复 - 10%
    ];

    // 如果步骤数不匹配，使用线性权重
    const weights =
      stepWeights.length === totalSteps
        ? stepWeights
        : Array(totalSteps).fill(1 / totalSteps);

    let progress = 0;

    // 计算已完成步骤的进度
    for (let i = 0; i < step && i < weights.length; i++) {
      progress += weights[i] * 100;
    }

    // 当前步骤的进度（假设当前步骤完成30%，表示正在进行中）
    if (step < weights.length && step < totalSteps) {
      progress += weights[step] * 30; // 当前步骤完成30%
    } else if (step >= totalSteps - 1) {
      // 如果是最后一步，显示100%
      progress = 100;
    }

    return Math.min(Math.max(progress, 0), 100);
  };

  const conversationLoadingSteps = [
    "正在加载对话历史...",
    "正在解析消息...",
    "准备就绪",
  ];

  const loadDocuments = useCallback(async () => {
    try {
      // 从统一的后端服务查询文档列表
      const result = await apiClient.listDocuments();
      if (result.error) {
        console.warn("加载文档列表失败:", result.error);
        // 如果服务不可用，返回空列表，不影响聊天功能
        setDocuments([]);
      } else if (result.data) {
        setDocuments(result.data.documents || []);
      }
    } catch (err) {
      console.warn("加载文档列表失败:", err);
      // 如果服务不可用，返回空列表，不影响聊天功能
      setDocuments([]);
    }
  }, []);

  const loadKnowledgeSpaces = useCallback(async () => {
    setIsLoadingKnowledgeSpaces(true);
    try {
      const result = await apiClient.listKnowledgeSpaces();
      if (result.error) {
        console.warn("加载知识空间列表失败:", result.error);
        setKnowledgeSpaces([]);
        setSelectedKnowledgeSpaceIds([]);
      } else if (result.data && result.data.knowledge_spaces) {
        const list = result.data.knowledge_spaces;
        setKnowledgeSpaces(list);

        // 默认选中默认知识空间；如果之前已选择，保持不变
        const defaultSpace = list.find((s) => s.is_default) || list[0];
        setSelectedKnowledgeSpaceIds((prev) => {
          if (prev && prev.length > 0) return prev;
          return defaultSpace?.id ? [defaultSpace.id] : [];
        });
      } else {
        setKnowledgeSpaces([]);
        setSelectedKnowledgeSpaceIds([]);
      }
    } catch (err) {
      console.warn("加载知识空间列表失败:", err);
      setKnowledgeSpaces([]);
      setSelectedKnowledgeSpaceIds([]);
    } finally {
      setIsLoadingKnowledgeSpaces(false);
    }
  }, []);

  // 轮询附件处理状态
  const pollAttachmentStatus = useCallback(
    async (convId: string, fileId: string, fileName: string) => {
      const poll = async () => {
        try {
          const result = await apiClient.getConversationAttachmentStatus(
            convId,
            fileId,
          );
          if (result.data) {
            const status = result.data.status;
            const progress = result.data.progress_percentage || 0;
            const stage = result.data.current_stage || "";
            const stageDetails = result.data.stage_details || "";

            // 更新文件状态
            setUploadedFiles((prev) =>
              prev.map((f) =>
                f.id === fileId
                  ? {
                      ...f,
                      status: status as
                        | "uploading"
                        | "processing"
                        | "completed"
                        | "failed",
                      progress,
                      stage,
                      stageDetails,
                    }
                  : f,
              ),
            );

            // 如果处理完成或失败，停止轮询
            if (status === "completed" || status === "failed") {
              const intervalId = statusPollingRef.current.get(fileId);
              if (intervalId) {
                clearInterval(intervalId);
                statusPollingRef.current.delete(fileId);
              }

              if (status === "completed") {
                // 显示完成消息（使用后端返回的详细信息）
                const completionMessage =
                  result.data.message ||
                  `文件 "${fileName}" 已成功处理完成。文件内容已被解析、分块并向量化存储到当前对话的专用向量空间中，现在可以开始对话了。`;

                const successMessage: MessageType = {
                  role: "assistant",
                  content: completionMessage,
                  timestamp: new Date().toISOString(),
                };
                setMessages((prev) => [...prev, successMessage]);

                // 滚动到底部显示新消息
                setTimeout(() => {
                  messagesEndRef.current?.scrollIntoView({
                    behavior: "smooth",
                  });
                }, 100);
              } else {
                // 显示失败消息
                const errorMessageText =
                  result.data.message ||
                  result.data.stage_details ||
                  "未知错误";

                const errorMessage: MessageType = {
                  role: "assistant",
                  content: `文件 "${fileName}" 处理失败：${errorMessageText}`,
                  timestamp: new Date().toISOString(),
                };
                setMessages((prev) => [...prev, errorMessage]);

                // 滚动到底部显示错误消息
                setTimeout(() => {
                  messagesEndRef.current?.scrollIntoView({
                    behavior: "smooth",
                  });
                }, 100);
              }
              return;
            }

            // 继续轮询
            const intervalId = setTimeout(poll, 2000); // 每2秒轮询一次
            statusPollingRef.current.set(fileId, intervalId);
          }
        } catch (error) {
          console.error("查询附件状态失败:", error);
          // 即使查询失败也继续轮询
          const intervalId = setTimeout(poll, 2000);
          statusPollingRef.current.set(fileId, intervalId);
        }
      };

      // 立即执行一次，然后开始轮询
      poll();
    },
    [],
  );

  // 保存状态到localStorage
  const saveStateToStorage = useCallback(() => {
    if (typeof window === "undefined") return;

    try {
      const storageKey = getStorageKey();
      const state = {
        messages,
        isLoading,
        loadingStep,
        conversationId,
        pendingContent: pendingContentRef.current,
        isStreaming: isStreamingRef.current,
        agentStatuses,
        deepResearchResults,
        timestamp: Date.now(),
      };
      localStorage.setItem(storageKey, JSON.stringify(state));
    } catch (error) {
      console.warn("保存状态失败:", error);
    }
  }, [
    messages,
    isLoading,
    loadingStep,
    conversationId,
    agentStatuses,
    deepResearchResults,
    getStorageKey,
  ]);

  // 从localStorage恢复状态
  const restoreStateFromStorage = useCallback(() => {
    if (typeof window === "undefined") return false;

    try {
      const storageKey = getStorageKey();
      const savedState = localStorage.getItem(storageKey);
      if (!savedState) return false;

      const state = JSON.parse(savedState);
      // 只恢复正在流式生成的状态（5分钟内）
      const isRecent =
        state.timestamp && Date.now() - state.timestamp < 5 * 60 * 1000;
      if (!isRecent || !state.isStreaming) {
        localStorage.removeItem(storageKey);
        return false;
      }

      // 恢复状态
      setIsLoading(state.isLoading || false);
      setLoadingStep(state.loadingStep || 0);
      isStreamingRef.current = state.isStreaming || false;

      // 恢复pendingContent到ref
      if (state.pendingContent) {
        pendingContentRef.current = state.pendingContent;
      }

      // 恢复消息列表，如果正在生成，确保最后一条助手消息显示pendingContent
      if (state.messages && state.messages.length > 0) {
        const updatedMessages = [...state.messages];
        // 如果正在生成且有pendingContent，更新最后一条助手消息
        if (
          state.isStreaming &&
          state.pendingContent &&
          updatedMessages.length > 0
        ) {
          const lastMessage = updatedMessages[updatedMessages.length - 1];
          if (lastMessage.role === "assistant") {
            updatedMessages[updatedMessages.length - 1] = {
              ...lastMessage,
              content: state.pendingContent,
            };
          }
        }
        setMessages(updatedMessages);
      }
      if (state.agentStatuses && state.agentStatuses.length > 0) {
        setAgentStatuses(state.agentStatuses);
      }
      if (state.deepResearchResults && state.deepResearchResults.length > 0) {
        setDeepResearchResults(state.deepResearchResults);
      }

      return true;
    } catch (error) {
      console.warn("恢复状态失败:", error);
      const storageKey = getStorageKey();
      localStorage.removeItem(storageKey);
      return false;
    }
  }, [getStorageKey]);

  // 清除保存的状态
  const clearSavedState = useCallback(() => {
    if (typeof window === "undefined") return;
    try {
      const storageKey = getStorageKey();
      localStorage.removeItem(storageKey);
    } catch (error) {
      console.warn("清除状态失败:", error);
    }
  }, [getStorageKey]);

  // 使用 ref 来存储函数，避免依赖项变化导致的重新渲染
  const saveStateToStorageRef = useRef(saveStateToStorage);
  const restoreStateFromStorageRef = useRef(restoreStateFromStorage);

  // 更新 ref
  useEffect(() => {
    saveStateToStorageRef.current = saveStateToStorage;
    restoreStateFromStorageRef.current = restoreStateFromStorage;
  }, [saveStateToStorage, restoreStateFromStorage]);

  // 点击空白处关闭知识空间选择器
  useEffect(() => {
    if (!spacePickerOpen) return;
    const onDown = (e: MouseEvent) => {
      const el = spacePickerRef.current;
      if (!el) return;
      if (e.target instanceof Node && el.contains(e.target)) return;
      setSpacePickerOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [spacePickerOpen]);

  useEffect(() => {
    setMounted(true);

    const fetchModels = async () => {
      try {
        const result = await apiClient.listModels();
        if (result.data) {
          setModels(result.data.models);
          if (result.data.models.length > 0) {
            // Try to set defaults if not already set
            const llm =
              result.data.models.find((m) => m.name.includes("gemma")) ||
              result.data.models[0];
            const embed =
              result.data.models.find(
                (m) => m.name.includes("embed") || m.name.includes("nomic"),
              ) || result.data.models[0];

            setSelectedLLM((prev) => prev || llm.name);
            setSelectedEmbedding((prev) => prev || embed.name);
          }
        }
      } catch (e) {
        console.error("Failed to fetch models", e);
      }
    };
    fetchModels();

    // 尝试恢复状态（只在首次加载时）
    const restored = restoreStateFromStorageRef.current();
    if (restored) {
      // 显示提示
      setToast({
        isOpen: true,
        message: "已恢复之前的对话状态",
        type: "info",
      });
      // 如果正在生成，滚动到底部显示最新内容
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 100);
    }

    // 监听来自 Navbar 的打开侧边栏事件
    const handleOpenSidebar = () => {
      setSidebarOpen(true);
    };

    window.addEventListener("openChatSidebar", handleOpenSidebar);

    // 监听页面可见性变化
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // 页面隐藏时保存状态
        saveStateToStorageRef.current();
      } else {
        // 页面显示时尝试恢复状态
        restoreStateFromStorageRef.current();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    // 监听页面卸载前保存状态
    const handleBeforeUnload = () => {
      if (isStreamingRef.current || isLoading) {
        saveStateToStorageRef.current();
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);

    // 定期保存状态（每5秒，仅在流式生成时）
    const intervalId = setInterval(() => {
      if (isStreamingRef.current || isLoading) {
        saveStateToStorageRef.current();
      }
    }, 5000);

    return () => {
      window.removeEventListener("openChatSidebar", handleOpenSidebar);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("beforeunload", handleBeforeUnload);
      clearInterval(intervalId);
      // 清理时保存状态
      if (isStreamingRef.current || isLoading) {
        saveStateToStorageRef.current();
      }
    };
  }, []); // 空依赖数组，只在组件挂载时运行一次

  useEffect(() => {
    const initialize = async () => {
      setIsInitializing(true);
      setInitStep(0);
      await new Promise((resolve) => setTimeout(resolve, 150));

      await loadKnowledgeSpaces();

      setInitStep(1);
      await loadDocuments();

      setInitStep(2);
      await new Promise((resolve) => setTimeout(resolve, 150));
      setIsInitializing(false);
    };

    initialize();
  }, [loadKnowledgeSpaces, loadDocuments]);

  // 智能滚动到底部（优化：只在必要时滚动，更丝滑的体验）
  const scrollToBottom = useCallback((force = false) => {
    if (!messagesEndRef.current || !messagesContainerRef.current) return;

    const container = messagesContainerRef.current;
    const scrollHeight = container.scrollHeight;
    const scrollTop = container.scrollTop;
    const clientHeight = container.clientHeight;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

    // 判断是否在底部附近（放宽阈值到150px，让用户更容易触发自动滚动）
    const isNearBottom = distanceFromBottom < 150;

    // 如果用户正在查看底部附近，或者强制滚动，或者正在流式输出，则滚动到底部
    if (force || isNearBottom || isStreamingRef.current) {
      // 使用 requestAnimationFrame 确保在 DOM 更新后执行
      requestAnimationFrame(() => {
        if (messagesEndRef.current) {
          // 如果用户已经在底部附近，使用更平滑的滚动
          // 如果距离底部很近（<50px），直接滚动到底部，不使用 smooth（更快）
          // 否则使用 smooth 滚动
          if (distanceFromBottom < 50 && !force) {
            // 直接设置 scrollTop，更快速
            container.scrollTop = scrollHeight;
          } else {
            // 使用 smooth 滚动，更丝滑
            messagesEndRef.current.scrollIntoView({
              behavior: "smooth",
              block: "end",
            });
          }
        }
      });
    }
  }, []);

  // 自动滚动到底部（当消息更新时，使用节流）
  useEffect(() => {
    // 如果正在流式输出，使用更频繁的滚动
    if (isStreamingRef.current) {
      // 使用 requestAnimationFrame 确保在 DOM 更新后滚动
      requestAnimationFrame(() => {
        scrollToBottom();
      });
    } else {
      // 否则延迟一点滚动，避免频繁滚动
      const timer = setTimeout(() => {
        scrollToBottom();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [messages, scrollToBottom]);

  // 组件卸载时清理定时器
  useEffect(() => {
    return () => {
      if (streamingUpdateTimerRef.current) {
        clearTimeout(streamingUpdateTimerRef.current);
        streamingUpdateTimerRef.current = null;
      }
      isStreamingRef.current = false;
      pendingContentRef.current = "";
    };
  }, []);

  // 快捷提示词：知识空间不承载提示词配置，这里保持空列表
  useEffect(() => {
    setQuickPromptsRotationIndex(0);
    setDisplayedQuickPrompts([]);
  }, [selectedKnowledgeSpaceIds.join(","), messages.length]);

  useEffect(() => {
    // 当对话ID变化时，保存当前对话的消息到本地缓存（用于快速访问）
    if (conversationId && messages.length > 0) {
      // 保存消息到localStorage作为缓存
      localStorage.setItem(
        `conversation_${conversationId}_messages`,
        JSON.stringify(messages),
      );

      // 注意：更新对话标题功能已移除，仅保留本地缓存更新
      // 对话标题会在创建时设置，后续不再更新
    }
  }, [conversationId, messages]);

  // 清理轮询定时器
  useEffect(() => {
    return () => {
      statusPollingRef.current.forEach((intervalId) => {
        clearInterval(intervalId);
      });
      statusPollingRef.current.clear();
    };
  }, []);

  const handleStopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
      setLoadingStep(0);
      isStreamingRef.current = false;
      pendingContentRef.current = "";
      if (streamingUpdateTimerRef.current) {
        clearTimeout(streamingUpdateTimerRef.current);
        streamingUpdateTimerRef.current = null;
      }
      setToast({
        isOpen: true,
        message: "已停止生成",
        type: "info",
      });
    }
  }, []);

  // 初始化加载状态
  if (isInitializing) {
    return (
      <Layout>
        <div className="flex min-h-[20vh] items-center justify-center">
          <LoadingProgress
            steps={initSteps}
            currentStep={initStep}
            className="min-h-[40vh]"
          />
        </div>
      </Layout>
    );
  }

  const handleSend = async (messageContent?: string) => {
    // 如果提供了消息内容，使用它；否则使用输入框的内容
    const contentToSend = messageContent || input.trim();
    if (!contentToSend || isLoading) return;

    // 检查是否有正在处理中的附件
    const hasProcessingFiles = uploadedFiles.some(
      (f) => f.status === "uploading" || f.status === "processing",
    );
    if (hasProcessingFiles) {
      alert("请等待附件上传和处理完成后再发送消息");
      return;
    }

    // AbortController
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const userMessage: MessageType = {
      role: "user",
      content: contentToSend,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);
    setLoadingStep(0);

    let currentConversationId = conversationId;
    let context = "";
    let sources: SourceInfo[] = [];
    let evidence: EvidenceItem[] = [];
    let evidenceQuality: EvidenceQuality | undefined;
    let citationWarnings: string[] = [];
    let citationQuality: CitationQuality | undefined;
    let recommendedResources: any[] = [];
    /** RAG 评测计时（仅常规模式） */
    let retrievalStartMs = 0;
    let retrievalTimeMs: number | undefined;
    let responseStartMs = 0;
    let responseTimeMs: number | undefined;
    let ttftMs: number | undefined;

    // Model Config
    const generationConfig = {
      llm_model: selectedLLM,
      embedding_model: selectedEmbedding,
    };

    try {
      // 1. 如果是新对话，创建对话记录（后端 API）
      if (!currentConversationId) {
        setLoadingStep(0);
        const title =
          input.trim().length > 30
            ? input.trim().substring(0, 30) + "..."
            : input.trim();
        const convResult = await apiClient.createConversation(title);
        if (convResult.data) {
          currentConversationId = convResult.data.id;
          setConversationId(currentConversationId);
          if (currentConversationId) {
            const newConversation: Conversation = {
              id: currentConversationId,
              title,
              createdAt: convResult.data.created_at,
              updatedAt: convResult.data.updated_at,
            };
            addConversation(newConversation);
          }
        }
      }

      // 2. 保存用户消息到对话历史（后端 API）
      setLoadingStep(1);
      if (currentConversationId) {
        await apiClient.addMessageToConversation(
          currentConversationId,
          "user",
          userMessage.content,
        );
        // 重新加载对话以获取消息ID并更新本地消息
        const convResult = await apiClient.getConversation(
          currentConversationId,
        );
        if (convResult.data && convResult.data.messages.length > 0) {
          const lastMessage =
            convResult.data.messages[convResult.data.messages.length - 1];
          // 更新本地消息，添加message_id
          setMessages((prev) => {
            const updated = [...prev];
            if (
              updated.length > 0 &&
              updated[updated.length - 1].role === "user"
            ) {
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                message_id: lastMessage.message_id,
              };
            }
            return updated;
          });
        }
      }

      // 3. 先分析查询，判断是否需要检索（如果启用了RAG增强模式则总是检索）
      let needRetrieval = false;

      if (enableRAG) {
        needRetrieval = true;
      } else {
        try {
          const analysisResult = await apiClient.analyzeQuery(
            userMessage.content,
          );
          if (analysisResult.data) {
            needRetrieval = analysisResult.data.need_retrieval;
          }
        } catch (error) {
          console.warn("查询分析失败，默认需要检索:", error);
          needRetrieval = true;
        }
      }

      // 4. 如果需要检索，执行RAG检索（步骤2）
      let hasContext = false;

      if (needRetrieval) {
        setLoadingStep(2); // 步骤2: 检索知识库
        retrievalStartMs = Date.now();
        try {
          const retrievalResult = await apiClient.retrieve({
            query: userMessage.content,
            document_id: selectedDocumentId,
            top_k: 100,
            knowledge_space_ids: selectedKnowledgeSpaceIds,
            conversation_id: currentConversationId,
          });
          if (retrievalResult.data) {
            context = retrievalResult.data.context || "";
            sources = retrievalResult.data.sources || [];
            evidence = retrievalResult.data.evidence || [];
            recommendedResources =
              retrievalResult.data.recommended_resources || [];
            hasContext = context.length > 0;
          }
          retrievalTimeMs = Date.now() - retrievalStartMs;
        } catch (error) {
          console.warn("RAG检索失败，继续不使用上下文:", error);
          retrievalTimeMs = Date.now() - retrievalStartMs;
        }
      } else {
        setLoadingStep(2);
        context = "";
        sources = [];
        hasContext = false;
      }

      // 5. 增强上下文（如果有检索到内容）（步骤3）
      if (hasContext) {
        setLoadingStep(3);
        await new Promise((resolve) => setTimeout(resolve, 150));
      } else {
        setLoadingStep(3);
      }

      // 6. 获取文档信息和知识库状态（省略，保持原有逻辑结构）
      // ... (Keeping simple for now, can add back if needed)

      // 7. 深度研究价值门控（先判断值不值得进入深度研究）
      let shouldUseDeepResearch =
        deepResearchEnabled && deepResearchFeatureEnabled;
      if (shouldUseDeepResearch) {
        const gate = await apiClient.evaluateDeepResearch({
          message: userMessage.content,
          conversation_id: currentConversationId,
        });
        if (gate.data) {
          const topReasons = gate.data.reasons.slice(0, 2).join("；");
          if (!gate.data.should_deep_research) {
            shouldUseDeepResearch = false;
            setAgentStatuses([]);
            setDeepResearchResults([]);
            setToast({
              isOpen: true,
              message: `本次问题评分 ${gate.data.score}/${gate.data.threshold}，先走常规模式：${topReasons}`,
              type: "info",
            });
          } else {
            setToast({
              isOpen: true,
              message: `已进入深度研究（评分 ${gate.data.score}/${gate.data.threshold}）：${topReasons}`,
              type: "warning",
            });
          }
        } else if (gate.error) {
          // 评估失败时保守降级到常规模式，避免直接触发高成本流程
          shouldUseDeepResearch = false;
          setAgentStatuses([]);
          setDeepResearchResults([]);
          setToast({
            isOpen: true,
            message: `深度研究预评估失败，已改走常规模式：${gate.error}`,
            type: "warning",
          });
        }
      }

      // 8. 根据模式选择调用不同的API - 开始生成回复
      setLoadingStep(4); // 步骤4: 生成回复

      // 深度研究模式
      if (shouldUseDeepResearch) {
        // 每次启动深度研究模式时都显示提示
        setToast({
          isOpen: true,
          message:
            "⚠️ 深度研究模式生成时间较长，通常需要5-10分钟，流量高峰期可能需要更长时间，请耐心等待。",
          type: "warning",
        });

        // 初始化所有Agent状态（确保所有Agent都显示）
        const startTime = Date.now();
        const allAgentTypes = [
          "coordinator",
          "document_retrieval",
          "argument_analysis",
          "concept_explanation",
          "critic",
          "summary",
          "formula_analysis",
          "code_analysis",
          "example_generation",
          "exercise",
          "scientific_coding",
        ];

        setAgentStatuses(
          allAgentTypes.map((agentType, index) => {
            if (index === 0) {
              return {
                agent_type: agentType,
                status: "running" as const,
                current_step: "分析用户问题，规划研究任务...",
                progress: 0,
                started_at: startTime,
              };
            }
            return {
              agent_type: agentType,
              status: "pending" as const,
            };
          }),
        );

        // 创建助手消息用于显示深度研究结果
        const assistantMessage: MessageType = {
          role: "assistant",
          content: "",
          timestamp: new Date().toISOString(),
          sources: [],
          recommended_resources: [],
        };
        setMessages((prev) => [...prev, assistantMessage]);
        setDeepResearchResults([]);

        isStreamingRef.current = true;
        setTimeout(() => saveStateToStorage(), 100);

        // 调用深度研究API
        const stream = await apiClient.deepResearchChat(
          {
            message: userMessage.content,
            conversation_id: currentConversationId,
            enabled_agents:
              deepThinkingAgents.length > 0 ? deepThinkingAgents : undefined,
            generation_config: generationConfig,
          },
          abortController.signal,
        );

        if (!stream) {
          throw new Error("无法连接到深度研究服务");
        }

        const reader = stream.getReader();
        const decoder = new TextDecoder();
        const agentResultsMap = new Map<
          string,
          { agent_type: string; content: string; title?: string }
        >();

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split("\n");

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const data = line.slice(6);
                if (data.trim() === "") continue;

                try {
                  const parsed = JSON.parse(data);

                  if (parsed.type === "planning") {
                    // 更新协调Agent状态为完成
                    const selectedAgents = parsed.selected_agents || [];

                    setAgentStatuses((prev) => {
                      let updated = prev.map((a) =>
                        a.agent_type === "coordinator"
                          ? {
                              ...a,
                              status: "completed" as const,
                              completed_at: Date.now(),
                              details:
                                parsed.reasoning ||
                                parsed.content ||
                                "任务规划完成",
                            }
                          : a,
                      );

                      updated = allAgentTypes.map((agentType) => {
                        if (agentType === "coordinator") {
                          const existing = updated.find(
                            (a) => a.agent_type === agentType,
                          );
                          return (
                            existing || {
                              agent_type: agentType,
                              status: "completed" as const,
                              completed_at: Date.now(),
                              details: parsed.reasoning || "任务规划完成",
                            }
                          );
                        }

                        const existing = updated.find(
                          (a) => a.agent_type === agentType,
                        );
                        if (selectedAgents.includes(agentType)) {
                          if (existing)
                            return { ...existing, status: "pending" as const };
                          return {
                            agent_type: agentType,
                            status: "pending" as const,
                          };
                        } else {
                          if (existing)
                            return {
                              ...existing,
                              status: "skipped" as const,
                              reason:
                                parsed.reasoning || "协调型Agent未选择此Agent",
                            };
                          return {
                            agent_type: agentType,
                            status: "skipped" as const,
                            reason:
                              parsed.reasoning || "协调型Agent未选择此Agent",
                          };
                        }
                      });

                      const nextAgent = updated.find(
                        (a) => a.status === "pending",
                      );
                      if (nextAgent) {
                        return updated.map((a) =>
                          a.agent_type === nextAgent.agent_type
                            ? {
                                ...a,
                                status: "running" as const,
                                started_at: Date.now(),
                                current_step: "开始工作...",
                              }
                            : a,
                        );
                      }
                      return updated;
                    });
                  } else if (parsed.type === "agent_status") {
                    setAgentStatuses((prev) => {
                      const agentExists = prev.some(
                        (a) => a.agent_type === parsed.agent_type,
                      );
                      const updated = agentExists
                        ? prev.map((a) =>
                            a.agent_type === parsed.agent_type
                              ? {
                                  ...a,
                                  status:
                                    (parsed.status as
                                      | "pending"
                                      | "running"
                                      | "completed"
                                      | "error"
                                      | "skipped") || a.status,
                                  progress:
                                    parsed.progress !== undefined
                                      ? parsed.progress
                                      : a.progress,
                                  current_step:
                                    parsed.current_step || a.current_step,
                                  details: parsed.details || a.details,
                                  started_at: parsed.started_at || a.started_at,
                                  completed_at:
                                    parsed.completed_at || a.completed_at,
                                }
                              : a,
                          )
                        : [
                            ...prev,
                            {
                              agent_type: parsed.agent_type,
                              status:
                                (parsed.status as
                                  | "pending"
                                  | "running"
                                  | "completed"
                                  | "error"
                                  | "skipped") || ("pending" as const),
                              progress: parsed.progress,
                              current_step: parsed.current_step,
                              details: parsed.details,
                              started_at: parsed.started_at,
                              completed_at: parsed.completed_at,
                            },
                          ];
                      setTimeout(() => saveStateToStorage(), 100);
                      return updated;
                    });
                  } else if (parsed.type === "agent_result") {
                    const completedTime = Date.now();
                    setAgentStatuses((prev) => {
                      const updated = prev.map((a) =>
                        a.agent_type === parsed.agent_type
                          ? {
                              ...a,
                              status: "completed" as const,
                              completed_at: completedTime,
                              details: parsed.title || "工作完成",
                            }
                          : a,
                      );
                      const nextAgent = updated.find(
                        (a) => a.status === "pending",
                      );
                      if (nextAgent) {
                        return updated.map((a) =>
                          a.agent_type === nextAgent.agent_type
                            ? {
                                ...a,
                                status: "running" as const,
                                started_at: Date.now(),
                                current_step: "开始工作...",
                              }
                            : a,
                        );
                      }
                      return updated;
                    });

                    if (parsed.agent_type && parsed.content) {
                      agentResultsMap.set(parsed.agent_type, {
                        agent_type: parsed.agent_type,
                        content: parsed.content,
                        title: parsed.title,
                      });
                      const updatedResults = Array.from(
                        agentResultsMap.values(),
                      );
                      setDeepResearchResults(updatedResults);
                      setTimeout(() => saveStateToStorage(), 100);
                    }
                  } else if (
                    parsed.type === "markdown" ||
                    parsed.type === "text"
                  ) {
                    if (parsed.content) {
                      const agentType = parsed.agent_type || "summary";
                      agentResultsMap.set(agentType, {
                        agent_type: agentType,
                        content: parsed.content,
                        title: parsed.title,
                      });
                      const updatedResults = Array.from(
                        agentResultsMap.values(),
                      );
                      setDeepResearchResults(updatedResults);
                      setTimeout(() => saveStateToStorage(), 100);
                    }
                  } else if (parsed.done) {
                    setAgentStatuses((prev) =>
                      prev.map((a) => ({
                        ...a,
                        status: (a.status === "running"
                          ? "completed"
                          : a.status) as
                          | "pending"
                          | "running"
                          | "completed"
                          | "error"
                          | "skipped",
                        completed_at: a.completed_at || Date.now(),
                      })),
                    );
                    break;
                  } else if (parsed.error) {
                    setAgentStatuses((prev) =>
                      prev.map((a) =>
                        a.status === "running"
                          ? {
                              ...a,
                              status: "error" as const,
                              details: parsed.error,
                            }
                          : a,
                      ),
                    );
                    throw new Error(parsed.error);
                  }
                } catch (e) {
                  // JSON解析失败，忽略
                }
              }
            }
          }
        } finally {
          reader.releaseLock();
        }

        const finalContent = Array.from(agentResultsMap.values())
          .map((result) => {
            const title = result.title || result.agent_type;
            return `## ${title}\n\n${result.content}`;
          })
          .join("\n\n---\n\n");

        setLoadingStep(5);
        if (currentConversationId && finalContent) {
          await apiClient.addMessageToConversation(
            currentConversationId,
            "assistant",
            finalContent,
            [],
            [],
          );
        }
        scrollToBottom(true);
      } else {
        // 常规模式
        let fullResponse = "";

        const assistantMessage: MessageType = {
          role: "assistant",
          content: "",
          timestamp: new Date().toISOString(),
          sources: sources.length > 0 ? sources : undefined,
          evidence: evidence.length > 0 ? evidence : undefined,
          evidence_quality: evidenceQuality,
          citation_warnings:
            citationWarnings.length > 0 ? citationWarnings : undefined,
          citation_quality: citationQuality,
          recommended_resources:
            recommendedResources.length > 0 ? recommendedResources : undefined,
        };

        setMessages((prev) => [...prev, assistantMessage]);

        isStreamingRef.current = true;
        responseStartMs = Date.now();
        const chatStream = await apiClient.chat(
          {
            message: userMessage.content,
            conversation_id: currentConversationId,
            knowledge_space_ids: selectedKnowledgeSpaceIds,
            enable_rag: enableRAG,
            generation_config: generationConfig,
          },
          abortController.signal,
        );

        if (!chatStream) {
          throw new Error("无法连接到聊天服务");
        }

        const reader = chatStream.getReader();
        const decoder = new TextDecoder();
        let firstContentReceived = true;

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split("\n");

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const data = line.slice(6);
                if (data.trim() === "") continue;

                try {
                  const parsed = JSON.parse(data);

                  if (parsed.content) {
                    if (firstContentReceived) {
                      ttftMs = Date.now() - responseStartMs;
                      firstContentReceived = false;
                    }
                    const chunkText = parsed.content;
                    fullResponse += chunkText;
                    pendingContentRef.current = fullResponse;

                    if (loadingStep < 4) {
                      setLoadingStep(4);
                    }

                    if (!streamingUpdateTimerRef.current) {
                      streamingUpdateTimerRef.current = setTimeout(() => {
                        const contentToUpdate = pendingContentRef.current;
                        setMessages((prev) => {
                          const updated = [...prev];
                          const lastMessage = updated[updated.length - 1];
                          if (lastMessage && lastMessage.role === "assistant") {
                            updated[updated.length - 1] = {
                              ...lastMessage,
                              content: contentToUpdate,
                              sources: lastMessage.sources,
                              evidence: lastMessage.evidence,
                              evidence_quality: lastMessage.evidence_quality,
                              citation_warnings: lastMessage.citation_warnings,
                              citation_quality: lastMessage.citation_quality,
                              recommended_resources:
                                lastMessage.recommended_resources,
                            };
                          }
                          return updated;
                        });
                        requestAnimationFrame(() => {
                          scrollToBottom();
                        });
                        if (saveStateTimerRef.current) {
                          clearTimeout(saveStateTimerRef.current);
                        }
                        saveStateTimerRef.current = setTimeout(() => {
                          saveStateToStorage();
                        }, 500);
                        streamingUpdateTimerRef.current = null;
                      }, 50);
                    }
                  } else if (parsed.done) {
                    if (parsed.sources) sources = parsed.sources;
                    if (parsed.evidence) evidence = parsed.evidence;
                    if (parsed.evidence_quality)
                      evidenceQuality = parsed.evidence_quality;
                    if (parsed.citation_warnings)
                      citationWarnings = parsed.citation_warnings;
                    if (parsed.citation_quality)
                      citationQuality = parsed.citation_quality;
                    if (parsed.recommended_resources)
                      recommendedResources = parsed.recommended_resources;
                    responseTimeMs = Date.now() - responseStartMs;
                    setLoadingStep(5);
                    break;
                  } else if (parsed.error) {
                    throw new Error(parsed.error);
                  }
                } catch (e) {
                  // JSON解析失败，忽略
                }
              }
            }
          }
        } finally {
          reader.releaseLock();
        }

        if (streamingUpdateTimerRef.current) {
          await new Promise<void>((resolve) => {
            const checkTimer = setInterval(() => {
              if (!streamingUpdateTimerRef.current) {
                clearInterval(checkTimer);
                resolve();
              }
            }, 10);
            setTimeout(() => {
              clearInterval(checkTimer);
              resolve();
            }, 100);
          });
        }

        if (fullResponse) {
          const ragMetrics: RAGEvaluationMetrics = {
            retrieval_triggered: needRetrieval,
            source_count: sources.length,
            context_length: context.length,
            retrieval_time_ms: retrievalTimeMs,
            time_to_first_token_ms: ttftMs,
            response_time_ms: responseTimeMs,
          };
          setMessages((prev) => {
            const updated = [...prev];
            const lastMessage = updated[updated.length - 1];
            if (lastMessage && lastMessage.role === "assistant") {
              updated[updated.length - 1] = {
                ...lastMessage,
                content: fullResponse,
                sources: sources.length > 0 ? sources : undefined,
                evidence: evidence.length > 0 ? evidence : undefined,
                evidence_quality: evidenceQuality,
                citation_warnings:
                  citationWarnings.length > 0 ? citationWarnings : undefined,
                citation_quality: citationQuality,
                recommended_resources:
                  recommendedResources.length > 0
                    ? recommendedResources
                    : undefined,
                rag_metrics: ragMetrics,
              };
            }
            return updated;
          });
        }

        isStreamingRef.current = false;
        pendingContentRef.current = "";
        clearSavedState();

        setLoadingStep(5);
        if (currentConversationId && fullResponse) {
          await apiClient.addMessageToConversation(
            currentConversationId,
            "assistant",
            fullResponse,
            sources.length > 0 ? sources : undefined,
            recommendedResources.length > 0 ? recommendedResources : undefined,
            evidence.length > 0 ? evidence : undefined,
            evidenceQuality,
            citationWarnings.length > 0 ? citationWarnings : undefined,
            citationQuality,
          );
        }
        scrollToBottom(true);
      }
    } catch (error: any) {
      if (error.name === "AbortError") {
        console.log("Generation aborted");
        const abortedMsg: MessageType = {
          role: "assistant",
          content: pendingContentRef.current + "\n\n[已停止生成]",
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => {
          const updated = [...prev];
          const lastMessage = updated[updated.length - 1];
          if (lastMessage && lastMessage.role === "assistant") {
            updated[updated.length - 1] = abortedMsg;
          }
          return updated;
        });

        if (currentConversationId && pendingContentRef.current) {
          try {
            await apiClient.addMessageToConversation(
              currentConversationId,
              "assistant",
              pendingContentRef.current + "\n\n[已停止生成]",
            );
          } catch (e) {
            console.error("保存停止消息失败", e);
          }
        }
      } else {
        const errorMessage = error.message || "未知错误";
        const errorMsg: MessageType = {
          role: "assistant",
          content: `抱歉，处理您的请求时出现错误: ${errorMessage}`,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, errorMsg]);

        if (currentConversationId) {
          try {
            await apiClient.addMessageToConversation(
              currentConversationId,
              "assistant",
              errorMsg.content,
            );
          } catch (e) {
            console.error("保存错误消息失败:", e);
          }
        }
      }
    } finally {
      setIsLoading(false);
      setLoadingStep(0);
      abortControllerRef.current = null;
    }
  };

  const handleNewConversation = () => {
    setConversationId(undefined);
    setMessages([]);
    setInput("");
  };

  const handleConversationSelect = async (id: string | undefined) => {
    if (id) {
      // 从 API 加载对话消息
      try {
        setIsLoading(true);
        setLoadingStep(0);

        // 步骤1: 加载对话历史
        setLoadingStep(0);
        const result = await apiClient.getConversation(id);
        if (result.error || !result.data) {
          console.error("加载对话失败:", result.error);
          setMessages([]);
          setConversationId(id);
          setIsLoading(false);
          setLoadingStep(0);
          return;
        }

        // 步骤2: 解析消息
        setLoadingStep(1);
        // 兼容旧字段 assistant_id：当前已改为“知识空间选择”，不再跟随对话切换
        const loadedMessages = result.data.messages.map((msg: any) => ({
          message_id: msg.message_id, // 包含消息ID
          role: msg.role,
          content: msg.content,
          timestamp: msg.timestamp || new Date().toISOString(),
          sources: msg.sources || [],
          evidence: msg.evidence || [],
          evidence_quality: msg.evidence_quality || undefined,
          citation_warnings: msg.citation_warnings || [],
          citation_quality: msg.citation_quality || undefined,
          recommended_resources: msg.recommended_resources || [],
        }));

        // 步骤3: 准备就绪
        setLoadingStep(2);
        await new Promise((resolve) => setTimeout(resolve, 200));

        setMessages(loadedMessages);
        setConversationId(id);

        // 同时更新本地缓存
        localStorage.setItem(
          `conversation_${id}_messages`,
          JSON.stringify(loadedMessages),
        );
      } catch (error) {
        console.error("加载对话消息失败:", error);
        setMessages([]);
        setConversationId(id);
      } finally {
        setIsLoading(false);
        setLoadingStep(0);
      }
    } else {
      // 新建对话
      handleNewConversation();
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = () => {
    // 上传前需要明确目标知识空间
    if (!selectedKnowledgeSpaceIds[0]) {
      setToast({
        isOpen: true,
        message: "请先选择要上传到的知识空间",
        type: "warning",
      });
      setSpacePickerOpen(true);
      return;
    }
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // 上传前需要明确目标知识空间
    const targetSpaceId = selectedKnowledgeSpaceIds[0];
    if (!targetSpaceId) {
      setToast({
        isOpen: true,
        message: "请先选择要上传到的知识空间",
        type: "warning",
      });
      setSpacePickerOpen(true);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    // 文件校验（与后端保持一致）
    const allowedExtensions = [
      ".pdf",
      ".docx",
      ".doc",
      ".md",
      ".txt",
      ".markdown",
    ];
    const lowerName = file.name.toLowerCase();
    const dot = lowerName.lastIndexOf(".");
    const ext = dot >= 0 ? lowerName.slice(dot) : "";
    if (!allowedExtensions.includes(ext)) {
      setToast({
        isOpen: true,
        message: "不支持的文件类型：仅支持 PDF/Word/Markdown/TXT",
        type: "warning",
      });
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    if (file.size === 0) {
      setToast({ isOpen: true, message: "文件不能为空", type: "warning" });
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    if (file.size > 200 * 1024 * 1024) {
      setToast({
        isOpen: true,
        message: "文件大小不能超过200MB",
        type: "warning",
      });
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    // 检查是否有对话ID，如果没有则先创建对话
    let currentConvId = conversationId;
    if (!currentConvId) {
      // 创建一个新对话
      const title =
        file.name.length > 30 ? file.name.substring(0, 30) + "..." : file.name;
      const convResult = await apiClient.createConversation(title);
      if (convResult.data) {
        currentConvId = convResult.data.id;
        setConversationId(currentConvId);
        const newConversation: Conversation = {
          id: currentConvId!,
          title,
          createdAt: convResult.data.created_at,
          updatedAt: convResult.data.updated_at,
        };
        addConversation(newConversation);
      } else {
        setToast({
          isOpen: true,
          message: "创建对话失败，无法上传文件",
          type: "error",
        });
        return;
      }
    }

    // 确保 currentConvId 不为空
    if (!currentConvId) {
      setToast({ isOpen: true, message: "无法获取对话ID", type: "error" });
      return;
    }

    // Type assertion to ensure string
    const validConvId = currentConvId as string;

    // 开始上传
    setUploadingFile(true);
    setUploadProgress(0);

    // 先添加文件到列表（上传中状态）
    const tempFileId = `temp-${Date.now()}`;
    setUploadedFiles((prev) => [
      ...prev,
      {
        name: file.name,
        id: tempFileId,
        status: "uploading",
        progress: 0,
      },
    ]);

    try {
      const result = await apiClient.uploadConversationAttachment(
        validConvId,
        targetSpaceId,
        file,
      );

      if (result.error) {
        throw new Error(result.error);
      }

      const fileId = result.data?.file_id || tempFileId;
      const initialStatus = result.data?.status || "processing";

      // 更新文件ID和状态
      setUploadedFiles((prev) =>
        prev.map((f) =>
          f.id === tempFileId
            ? {
                ...f,
                id: fileId,
                status: initialStatus as
                  | "uploading"
                  | "processing"
                  | "completed"
                  | "failed",
                progress: 100, // 上传完成
              }
            : f,
        ),
      );

      // 显示上传成功消息
      const uploadMessage: MessageType = {
        role: "assistant",
        content: `文件 "${file.name}" 已上传到知识空间，正在解析和处理中...`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, uploadMessage]);

      // 开始轮询处理状态
      if (initialStatus === "processing" || initialStatus === "uploading") {
        pollAttachmentStatus(validConvId, fileId, file.name);
      } else if (initialStatus === "completed") {
        // 如果已经完成，直接显示完成消息
        const successMessage: MessageType = {
          role: "assistant",
          content: `文件 "${file.name}" 已处理完成：已解析、分块并向量化入库到目标知识空间，可用于增强检索。`,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, successMessage]);
      }
    } catch (error) {
      const errorMessage = (error as Error).message || "上传失败";
      // 移除失败的文件
      setUploadedFiles((prev) => prev.filter((f) => f.id !== tempFileId));
      setToast({
        isOpen: true,
        message: `文件上传失败: ${errorMessage}`,
        type: "error",
      });
    } finally {
      setUploadingFile(false);
      setUploadProgress(0);
      // 清空文件输入
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleEditMessage = async (messageId: string, newContent: string) => {
    if (!conversationId) return;
    const currentConvId = conversationId;

    try {
      const result = await apiClient.updateMessage(
        currentConvId,
        messageId,
        newContent,
      );
      if (result.error) {
        throw new Error(result.error);
      }

      // 更新本地消息列表
      setMessages((prev) =>
        prev.map((msg) =>
          msg.message_id === messageId
            ? {
                ...msg,
                content: newContent,
                timestamp: result.data?.timestamp || msg.timestamp,
              }
            : msg,
        ),
      );

      // 保存后自动触发重新生成
      await handleRegenerateResponse(messageId);
    } catch (error) {
      console.error("编辑消息失败:", error);
      throw error;
    }
  };

  const handleRegenerateResponse = async (messageId: string) => {
    if (!conversationId) return;
    const currentConvId = conversationId;

    setIsLoading(true);
    setLoadingStep(0);

    try {
      // 1. 调用重新生成API，删除后续消息
      const regenerateResult = await apiClient.regenerateResponse(
        currentConvId,
        messageId,
      );
      if (regenerateResult.error) {
        throw new Error(regenerateResult.error);
      }

      // 2. 找到要重新生成的消息（必须是用户消息）
      const messageIndex = messages.findIndex(
        (msg) => msg.message_id === messageId,
      );
      if (messageIndex === -1) {
        throw new Error("找不到要重新生成的消息");
      }

      const editedMessage = messages[messageIndex];

      // 验证：只能重新生成用户消息对应的回答
      if (editedMessage.role !== "user") {
        throw new Error("只能重新生成用户消息对应的回答");
      }

      // 3. 删除该消息之后的所有消息
      setMessages((prev) => prev.slice(0, messageIndex + 1));

      // 4. 重新加载对话以获取最新的消息列表（包含message_id）
      const convResult = await apiClient.getConversation(currentConvId);
      if (convResult.data) {
        const loadedMessages = convResult.data.messages.map((msg: any) => ({
          message_id: msg.message_id,
          role: msg.role,
          content: msg.content,
          timestamp: msg.timestamp || new Date().toISOString(),
          sources: msg.sources || [],
          evidence: msg.evidence || [],
          evidence_quality: msg.evidence_quality || undefined,
          citation_warnings: msg.citation_warnings || [],
          citation_quality: msg.citation_quality || undefined,
          recommended_resources: msg.recommended_resources || [],
        }));
        setMessages(loadedMessages);
      }

      // 5. 重新生成回答（使用编辑后的消息内容）
      setLoadingStep(2);
      let context = "";
      let sources: SourceInfo[] = [];
      let evidence: EvidenceItem[] = [];
      let evidenceQuality: EvidenceQuality | undefined;
      let citationWarnings: string[] = [];
      let citationQuality: CitationQuality | undefined;
      let recommendedResources: any[] = [];

      // RAG检索知识空间（如果启用了RAG增强模式，总是检索）
      let hasContext = false;
      const selectedSpaces = knowledgeSpaces.filter((s) =>
        selectedKnowledgeSpaceIds.includes(s.id),
      );
      const assistantName =
        selectedSpaces.map((s) => s.name).join("、") || "默认知识空间";

      const shouldRetrieve =
        enableRAG || selectedKnowledgeSpaceIds.length > 0 || selectedDocumentId;

      if (shouldRetrieve) {
        try {
          // 传递对话ID（如果存在），后端会智能处理检索逻辑
          const retrievalResult = await apiClient.retrieve({
            query: editedMessage.content,
            document_id: selectedDocumentId,
            top_k: 5,
            knowledge_space_ids: selectedKnowledgeSpaceIds,
            conversation_id: currentConvId,
          });
          if (retrievalResult.data) {
            context = retrievalResult.data.context || "";
            sources = retrievalResult.data.sources || [];
            evidence = retrievalResult.data.evidence || [];
            recommendedResources =
              retrievalResult.data.recommended_resources || [];
            hasContext = context.length > 0;
          }
        } catch (error) {
          console.warn("RAG检索失败，继续不使用上下文:", error);
        }
      }

      // 增强上下文（如果有检索到内容）
      if (hasContext) {
        setLoadingStep(3);
        await new Promise((resolve) => setTimeout(resolve, 150));
      } else {
        setLoadingStep(3);
      }

      // 获取文档信息和知识库状态
      let documentInfo = undefined;
      let knowledgeBaseStatus = undefined;

      if (selectedDocumentId) {
        try {
          const docDetail =
            await apiClient.getDocumentDetail(selectedDocumentId);
          if (docDetail.data) {
            const metadata = docDetail.data.metadata || {};
            documentInfo = {
              title: docDetail.data.title,
              status: docDetail.data.status,
              file_type: docDetail.data.file_type,
              total_chunks: docDetail.data.total_chunks,
              total_vectors: docDetail.data.total_vectors,
              created_at: docDetail.data.created_at,
              author: metadata.author || "",
            };
          }
        } catch (error) {
          console.warn("获取文档详情失败:", error);
        }
      }

      const isAskingAboutKB =
        /知识库|文档列表|有哪些文档|多少文档|文档数量/i.test(
          editedMessage.content,
        );
      if (isAskingAboutKB) {
        try {
          const docsResult = await apiClient.listDocuments();
          if (docsResult.data) {
            const docs = docsResult.data.documents || [];
            const completed = docs.filter(
              (d: any) => d.status === "completed",
            ).length;
            const processing = docs.filter(
              (d: any) => d.status === "processing",
            ).length;
            const failed = docs.filter(
              (d: any) => d.status === "failed",
            ).length;

            knowledgeBaseStatus = {
              total: docs.length,
              completed,
              processing,
              failed,
              documents: docs.map((d: any) => ({
                title: d.title,
                status: d.status,
                created_at: d.created_at || "",
              })),
            };
          }
        } catch (error) {
          console.warn("获取知识库状态失败:", error);
        }
      }

      // 生成回复（使用新的 /chat 端点，模型会自动选择）
      setLoadingStep(4);
      let fullResponse = "";

      if (useStreaming) {
        // 流式输出模式
        const assistantMessage: MessageType = {
          role: "assistant",
          content: "",
          timestamp: new Date().toISOString(),
          sources: sources.length > 0 ? sources : undefined,
          evidence: evidence.length > 0 ? evidence : undefined,
          evidence_quality: evidenceQuality,
          citation_warnings:
            citationWarnings.length > 0 ? citationWarnings : undefined,
          citation_quality: citationQuality,
          recommended_resources:
            recommendedResources.length > 0 ? recommendedResources : undefined,
        };

        // 先添加空消息，然后流式更新
        setMessages((prev) => [...prev, assistantMessage]);

        try {
          // 使用新的 /chat 端点（流式）
          isStreamingRef.current = true;
          const chatStream = await apiClient.chat({
            message: editedMessage.content,
            conversation_id: currentConvId,
          });

          if (!chatStream) {
            throw new Error("无法连接到聊天服务");
          }

          const reader = chatStream.getReader();
          const decoder = new TextDecoder();

          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              const chunk = decoder.decode(value);
              const lines = chunk.split("\n");

              for (const line of lines) {
                if (line.startsWith("data: ")) {
                  const data = line.slice(6);
                  if (data.trim() === "") continue;

                  try {
                    const parsed = JSON.parse(data);

                    if (parsed.content) {
                      const chunkText = parsed.content;
                      fullResponse += chunkText;
                      pendingContentRef.current = fullResponse;

                      if (!streamingUpdateTimerRef.current) {
                        streamingUpdateTimerRef.current = setTimeout(() => {
                          const contentToUpdate = pendingContentRef.current;
                          setMessages((prev) => {
                            const updated = [...prev];
                            const lastMessage = updated[updated.length - 1];
                            if (
                              lastMessage &&
                              lastMessage.role === "assistant"
                            ) {
                              updated[updated.length - 1] = {
                                ...lastMessage,
                                content: contentToUpdate,
                                sources: lastMessage.sources,
                                evidence: lastMessage.evidence,
                                evidence_quality: lastMessage.evidence_quality,
                                citation_warnings:
                                  lastMessage.citation_warnings,
                                citation_quality: lastMessage.citation_quality,
                                recommended_resources:
                                  lastMessage.recommended_resources,
                              };
                            }
                            return updated;
                          });
                          requestAnimationFrame(() => {
                            scrollToBottom();
                          });
                          streamingUpdateTimerRef.current = null;
                        }, 50);
                      }
                    } else if (parsed.done) {
                      if (parsed.sources) sources = parsed.sources;
                      if (parsed.evidence) evidence = parsed.evidence;
                      if (parsed.evidence_quality)
                        evidenceQuality = parsed.evidence_quality;
                      if (parsed.citation_warnings)
                        citationWarnings = parsed.citation_warnings;
                      if (parsed.citation_quality)
                        citationQuality = parsed.citation_quality;
                      if (parsed.recommended_resources)
                        recommendedResources = parsed.recommended_resources;
                      break;
                    } else if (parsed.error) {
                      throw new Error(parsed.error);
                    }
                  } catch (e) {
                    // JSON解析失败，忽略
                  }
                }
              }
            }
          } finally {
            reader.releaseLock();
          }

          // 等待最后一个定时器
          if (streamingUpdateTimerRef.current) {
            await new Promise<void>((resolve) => {
              const checkTimer = setInterval(() => {
                if (!streamingUpdateTimerRef.current) {
                  clearInterval(checkTimer);
                  resolve();
                }
              }, 10);
              setTimeout(() => {
                clearInterval(checkTimer);
                resolve();
              }, 100);
            });
          }

          // 确保最后的内容被更新
          if (fullResponse) {
            setMessages((prev) => {
              const updated = [...prev];
              const lastMessage = updated[updated.length - 1];
              if (lastMessage && lastMessage.role === "assistant") {
                updated[updated.length - 1] = {
                  ...lastMessage,
                  content: fullResponse,
                  sources: sources.length > 0 ? sources : undefined,
                  evidence: evidence.length > 0 ? evidence : undefined,
                  evidence_quality: evidenceQuality,
                  citation_warnings:
                    citationWarnings.length > 0 ? citationWarnings : undefined,
                  citation_quality: citationQuality,
                  recommended_resources:
                    recommendedResources.length > 0
                      ? recommendedResources
                      : undefined,
                };
              }
              return updated;
            });
          }

          isStreamingRef.current = false;
          pendingContentRef.current = "";

          scrollToBottom(true);
        } catch (streamError) {
          // 如果流式生成失败，回退到非流式
          console.warn("流式生成失败，尝试非流式:", streamError);

          const chatResult = await apiClient.chat({
            message: editedMessage.content,
            conversation_id: conversationId,
          });

          if (chatResult && typeof chatResult.getReader === "function") {
            const reader = chatResult.getReader();
            const decoder = new TextDecoder();

            try {
              while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split("\n");

                for (const line of lines) {
                  if (line.startsWith("data: ")) {
                    const data = line.slice(6);
                    if (data.trim() === "") continue;

                    try {
                      const parsed = JSON.parse(data);
                      if (parsed.content) {
                        fullResponse += parsed.content;
                      } else if (parsed.done) {
                        if (parsed.sources) sources = parsed.sources;
                        if (parsed.evidence) evidence = parsed.evidence;
                        if (parsed.evidence_quality)
                          evidenceQuality = parsed.evidence_quality;
                        if (parsed.citation_warnings)
                          citationWarnings = parsed.citation_warnings;
                        if (parsed.citation_quality)
                          citationQuality = parsed.citation_quality;
                        if (parsed.recommended_resources)
                          recommendedResources = parsed.recommended_resources;
                      }
                    } catch (e) {
                      // 忽略解析错误
                    }
                  }
                }
              }
            } finally {
              reader.releaseLock();
            }
          }

          if (!fullResponse) {
            throw new Error("无法生成回复");
          }

          // 更新消息
          setMessages((prev) => {
            const updated = [...prev];
            const lastMessage = updated[updated.length - 1];
            if (lastMessage && lastMessage.role === "assistant") {
              updated[updated.length - 1] = {
                ...lastMessage,
                content: fullResponse,
                sources: sources.length > 0 ? sources : undefined,
                evidence: evidence.length > 0 ? evidence : undefined,
                evidence_quality: evidenceQuality,
                citation_warnings:
                  citationWarnings.length > 0 ? citationWarnings : undefined,
                citation_quality: citationQuality,
                recommended_resources:
                  recommendedResources.length > 0
                    ? recommendedResources
                    : undefined,
              };
            }
            return updated;
          });
        }
      } else {
        // 非流式输出模式 - 使用新的 /chat 端点
        const chatResult = await apiClient.chat({
          message: editedMessage.content,
          conversation_id: conversationId,
        });

        if (!chatResult || typeof chatResult.getReader !== "function") {
          throw new Error("无法连接到聊天服务");
        }

        const reader = chatResult.getReader();
        const decoder = new TextDecoder();

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split("\n");

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const data = line.slice(6);
                if (data.trim() === "") continue;

                try {
                  const parsed = JSON.parse(data);
                  if (parsed.content) {
                    fullResponse += parsed.content;
                  } else if (parsed.done) {
                    if (parsed.sources) sources = parsed.sources;
                    if (parsed.evidence) evidence = parsed.evidence;
                    if (parsed.evidence_quality)
                      evidenceQuality = parsed.evidence_quality;
                    if (parsed.citation_warnings)
                      citationWarnings = parsed.citation_warnings;
                    if (parsed.citation_quality)
                      citationQuality = parsed.citation_quality;
                    if (parsed.recommended_resources)
                      recommendedResources = parsed.recommended_resources;
                  }
                } catch (e) {
                  // 忽略解析错误
                }
              }
            }
          }
        } finally {
          reader.releaseLock();
        }

        if (!fullResponse) {
          throw new Error("无法生成回复");
        }

        const assistantMessage: MessageType = {
          role: "assistant",
          content: fullResponse,
          timestamp: new Date().toISOString(),
          sources: sources.length > 0 ? sources : undefined,
          evidence: evidence.length > 0 ? evidence : undefined,
          evidence_quality: evidenceQuality,
          citation_warnings:
            citationWarnings.length > 0 ? citationWarnings : undefined,
          citation_quality: citationQuality,
          recommended_resources:
            recommendedResources.length > 0 ? recommendedResources : undefined,
        };

        setMessages((prev) => [...prev, assistantMessage]);
      }

      // 保存助手回复
      setLoadingStep(5);
      if (conversationId && fullResponse) {
        await apiClient.addMessageToConversation(
          conversationId,
          "assistant",
          fullResponse,
          sources.length > 0 ? sources : undefined,
          recommendedResources.length > 0 ? recommendedResources : undefined,
          evidence.length > 0 ? evidence : undefined,
          evidenceQuality,
          citationWarnings.length > 0 ? citationWarnings : undefined,
          citationQuality,
        );
      }
    } catch (error) {
      const errorMessage = (error as Error).message || "未知错误";
      const errorMsg: MessageType = {
        role: "assistant",
        content: `抱歉，重新生成回答时出现错误: ${errorMessage}`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
      setLoadingStep(0);
    }
  };

  return (
    <Layout noPadding>
      <div className="flex h-full w-full">
        {/* 侧边栏 */}
        <ChatSidebar
          currentConversationId={conversationId}
          onConversationSelect={handleConversationSelect}
          onNewConversation={handleNewConversation}
          isOpen={sidebarOpen}
          onOpenChange={setSidebarOpen}
        />

        {/* 主聊天区域 */}
        <div className="flex-1 flex flex-col bg-white dark:bg-gray-900 min-w-0 overflow-hidden transition-colors">
          {/* 顶部工具栏 */}
          {mounted && (
            <div className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 sm:px-4 py-2 sm:py-3 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 sm:gap-4 flex-shrink-0 transition-colors">
              <div className="flex items-center gap-2 sm:gap-4 flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <span className="text-xs sm:text-sm text-gray-600 dark:text-gray-300 font-medium whitespace-nowrap hidden sm:inline">
                    知识空间
                  </span>
                  {isLoadingKnowledgeSpaces ? (
                    <span className="text-xs sm:text-sm text-gray-400 dark:text-gray-500">
                      加载中...
                    </span>
                  ) : (
                    <div className="relative" ref={spacePickerRef}>
                      {(() => {
                        const selectedSpaces = knowledgeSpaces.filter((s) =>
                          selectedKnowledgeSpaceIds.includes(s.id),
                        );
                        const label =
                          selectedSpaces.length === 0
                            ? "选择知识空间"
                            : selectedSpaces.length <= 2
                              ? selectedSpaces.map((s) => s.name).join("、")
                              : `${selectedSpaces[0]?.name} 等 ${selectedSpaces.length} 个`;
                        return (
                          <button
                            type="button"
                            onClick={() => setSpacePickerOpen((v) => !v)}
                            className="w-full sm:w-auto text-xs sm:text-sm px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 min-w-0 flex items-center justify-between gap-2 h-10 sm:min-w-[220px]"
                            suppressHydrationWarning
                            title="可多选：发起增强检索时将同时检索这些知识空间"
                          >
                            <span className="truncate">{label}</span>
                            <svg
                              className={`w-4 h-4 flex-shrink-0 transition-transform ${spacePickerOpen ? "rotate-180" : ""}`}
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M19 9l-7 7-7-7"
                              />
                            </svg>
                          </button>
                        );
                      })()}

                      {spacePickerOpen && (
                        <div className="absolute left-0 right-0 sm:left-auto sm:right-auto z-50 mt-2 w-full min-w-0 sm:w-[min(100vw-2rem,56rem)] max-w-[min(100vw-1rem,56rem)] rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-xl overflow-hidden">
                          <div className="p-3 border-b border-gray-200 dark:border-gray-700">
                            <div className="relative">
                              <input
                                value={spacePickerQuery}
                                onChange={(e) =>
                                  setSpacePickerQuery(e.target.value)
                                }
                                placeholder="搜索知识空间"
                                className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
                                autoFocus
                              />
                              <svg
                                className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M21 21l-4.35-4.35m1.85-5.15a7 7 0 11-14 0 7 7 0 0114 0z"
                                />
                              </svg>
                            </div>
                          </div>

                          <div className="max-h-[min(50vh,22rem)] overflow-y-auto p-2">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {knowledgeSpaces
                                .filter((s) => {
                                  const q = spacePickerQuery
                                    .trim()
                                    .toLowerCase();
                                  if (!q) return true;
                                  return (
                                    (s.name || "").toLowerCase().includes(q) ||
                                    (s.description || "")
                                      .toLowerCase()
                                      .includes(q)
                                  );
                                })
                                .map((s) => {
                                  const checked =
                                    selectedKnowledgeSpaceIds.includes(s.id);
                                  return (
                                    <label
                                      key={s.id}
                                      className="flex items-start gap-2.5 p-2.5 rounded-lg cursor-pointer border border-gray-100 dark:border-gray-800 bg-gray-50/80 dark:bg-gray-800/40 hover:bg-gray-100 dark:hover:bg-gray-800/80 min-w-0"
                                    >
                                      <input
                                        type="checkbox"
                                        checked={checked}
                                        onChange={(e) => {
                                          const next = e.target.checked
                                            ? Array.from(
                                                new Set([
                                                  ...selectedKnowledgeSpaceIds,
                                                  s.id,
                                                ]),
                                              )
                                            : selectedKnowledgeSpaceIds.filter(
                                                (id) => id !== s.id,
                                              );
                                          setSelectedKnowledgeSpaceIds(next);
                                        }}
                                        className="mt-0.5 w-4 h-4 shrink-0 text-blue-600 dark:text-blue-400 border-gray-300 dark:border-gray-600 rounded"
                                      />
                                      <div className="min-w-0 flex-1">
                                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100 break-words">
                                          {s.name}
                                          {s.is_default ? (
                                            <span className="text-xs text-gray-500 dark:text-gray-400 ml-1">
                                              （默认）
                                            </span>
                                          ) : null}
                                        </div>
                                        {s.description ? (
                                          <div className="text-xs text-gray-500 dark:text-gray-400 line-clamp-3 mt-0.5">
                                            {s.description}
                                          </div>
                                        ) : null}
                                      </div>
                                    </label>
                                  );
                                })}
                            </div>
                          </div>

                          <div className="p-2 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between gap-2">
                            <button
                              type="button"
                              onClick={() => setSelectedKnowledgeSpaceIds([])}
                              className="px-3 py-2 text-xs rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700"
                            >
                              清空
                            </button>
                            <button
                              type="button"
                              onClick={() => setSpacePickerOpen(false)}
                              className="px-3 py-2 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700"
                            >
                              完成
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* 模型配置按钮 */}
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setShowModelSettings((v) => !v)}
                    className="w-full sm:w-auto text-xs sm:text-sm px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 min-w-0 flex items-center justify-between gap-2 h-10"
                    title="模型配置"
                  >
                    <span className="hidden sm:inline">模型配置</span>
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                      />
                    </svg>
                  </button>

                  {showModelSettings && (
                    <div className="absolute right-0 z-50 mt-2 w-[320px] max-w-[90vw] rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-xl overflow-hidden p-4">
                      <div className="flex items-center justify-between mb-4 border-b border-gray-100 dark:border-gray-800 pb-2">
                        <h3 className="font-medium text-gray-900 dark:text-gray-100">
                          模型配置
                        </h3>
                        <button
                          onClick={() => setShowModelSettings(false)}
                          className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                        >
                          <svg
                            className="w-4 h-4"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M6 18L18 6M6 6l12 12"
                            />
                          </svg>
                        </button>
                      </div>

                      <div className="space-y-4">
                        <div>
                          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                            推理模型 (LLM)
                          </label>
                          <select
                            value={selectedLLM}
                            onChange={(e) => setSelectedLLM(e.target.value)}
                            className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                          >
                            <option value="">自动选择</option>
                            {models.map((m) => (
                              <option key={m.name} value={m.name}>
                                {m.name}
                                {m.details?.parameter_size != null
                                  ? ` (${m.details.parameter_size})`
                                  : ""}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div>
                          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                            向量模型 (Embedding)
                          </label>
                          <select
                            value={selectedEmbedding}
                            onChange={(e) =>
                              setSelectedEmbedding(e.target.value)
                            }
                            className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                          >
                            <option value="">自动选择</option>
                            {models.map((m) => (
                              <option key={m.name} value={m.name}>
                                {m.name}
                              </option>
                            ))}
                          </select>
                        </div>

                        {deepResearchEnabled && (
                          <div>
                            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                              深度思考子Agent
                            </label>
                            <div className="max-h-32 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg p-2 space-y-1">
                              {[
                                { id: "document_retrieval", name: "文档检索" },
                                { id: "summary", name: "总结归纳" },
                                { id: "concept_explanation", name: "概念解释" },
                                { id: "argument_analysis", name: "论证分析" },
                                { id: "critic", name: "批判性分析" },
                                { id: "scientific_coding", name: "实现方案" },
                              ].map((agent) => (
                                <label
                                  key={agent.id}
                                  className="flex items-center gap-2 text-xs"
                                >
                                  <input
                                    type="checkbox"
                                    checked={deepThinkingAgents.includes(
                                      agent.id,
                                    )}
                                    onChange={(e) => {
                                      if (e.target.checked) {
                                        setDeepThinkingAgents([
                                          ...deepThinkingAgents,
                                          agent.id,
                                        ]);
                                      } else {
                                        setDeepThinkingAgents(
                                          deepThinkingAgents.filter(
                                            (id) => id !== agent.id,
                                          ),
                                        );
                                      }
                                    }}
                                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                  />
                                  <span className="text-gray-700 dark:text-gray-300">
                                    {agent.name}
                                  </span>
                                </label>
                              ))}
                            </div>
                            <p className="text-[10px] text-gray-500 mt-1">
                              默认优先走 RAG
                              检索、解释、校验与总结链路；未选择则由协调Agent自动规划
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 消息区域 - ChatGPT风格 */}
          <div
            ref={messagesContainerRef}
            className="flex-1 overflow-y-auto bg-white dark:bg-gray-900 transition-colors px-3 sm:px-4 md:px-6 py-4 sm:py-6"
            style={{ scrollBehavior: "smooth" }}
          >
            {messages.length === 0 &&
              (() => {
                const selectedSpaces = knowledgeSpaces.filter((s) =>
                  selectedKnowledgeSpaceIds.includes(s.id),
                );
                const spaceLabel =
                  selectedSpaces.map((s) => s.name).join("、") ||
                  "默认知识空间";
                const greeting = `欢迎使用对话。当前增强检索空间：${spaceLabel}`;
                const quickPrompts: string[] = [];

                const handleQuickPrompt = (prompt: string) => {
                  if (isLoading) return;
                  // 直接发送，不需要设置输入框
                  handleSend(prompt);
                };

                return (
                  <div className="text-center text-gray-500 dark:text-gray-400 mt-8 sm:mt-12 md:mt-20 max-w-3xl mx-auto">
                    <p
                      className="text-lg sm:text-xl font-medium mb-2 sm:mb-3 text-gray-700 dark:text-gray-200"
                      suppressHydrationWarning
                    >
                      {greeting}
                    </p>
                    <p
                      className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mb-4 sm:mb-6"
                      suppressHydrationWarning
                    >
                      {selectedSpaces
                        .map((s) => s.description)
                        .filter((d): d is string => Boolean(d && d.trim()))
                        .join("；") || "请输入您的问题，我会尽力为您解答"}
                    </p>
                    {/* 快捷提示词按钮 */}
                    {quickPrompts.length > 0 && (
                      <div className="mt-4 sm:mt-6 md:mt-8">
                        <p className="text-[10px] sm:text-xs md:text-sm text-gray-400 dark:text-gray-500 mb-2 sm:mb-3 md:mb-4">
                          快捷提示词：
                        </p>
                        <div className="flex flex-wrap gap-1.5 sm:gap-2 md:gap-3 justify-center">
                          {quickPrompts.map((prompt, index) => (
                            <button
                              key={index}
                              onClick={() => handleQuickPrompt(prompt)}
                              disabled={isLoading}
                              className="px-2.5 sm:px-3 md:px-4 py-1.5 sm:py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-[11px] sm:text-xs md:text-sm text-gray-700 dark:text-gray-200 active:bg-blue-50 dark:active:bg-blue-900/30 active:border-blue-300 dark:active:border-blue-600 active:text-blue-700 dark:active:text-blue-400 transition-all duration-200 shadow-sm active:shadow-md disabled:opacity-50 disabled:cursor-not-allowed min-h-[36px] sm:min-h-[40px]"
                            >
                              {prompt}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}

            {messages.map((message, index) => {
              // 判断是否是最后一条助手消息且正在生成中
              const isLastAssistantMessage =
                message.role === "assistant" && index === messages.length - 1;
              const isGenerating =
                isLoading &&
                isLastAssistantMessage &&
                (!message.content || message.content.trim() === "");

              // 判断是否是深度研究模式的结果
              const isDeepResearchResult =
                deepResearchEnabled &&
                isLastAssistantMessage &&
                deepResearchResults.length > 0;

              return (
                <div key={message.message_id || index}>
                  {isDeepResearchResult ? (
                    <div className="flex w-full mb-4 sm:mb-6 items-start gap-2 sm:gap-3 justify-start animate-fadeIn">
                      {/* 助手头像 */}
                      <div className="flex-shrink-0 w-6 h-6 sm:w-8 sm:h-8 rounded-full overflow-hidden bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-md">
                        <svg
                          className="w-3.5 h-3.5 sm:w-5 sm:h-5 text-white"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                          />
                        </svg>
                      </div>

                      {/* 消息气泡 */}
                      <div className="flex flex-col items-start max-w-[85%] sm:max-w-[85%] md:max-w-[75%]">
                        <div className="relative group rounded-xl sm:rounded-xl md:rounded-2xl px-3.5 sm:px-4 md:px-5 py-3 sm:py-3 md:py-4 shadow-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-bl-sm hover:shadow-xl">
                          <DeepResearchRenderer
                            agentResults={deepResearchResults}
                          />
                        </div>

                        {/* 时间戳 */}
                        {message.timestamp && (
                          <div className="text-[10px] sm:text-xs mt-1 sm:mt-2 px-1 text-gray-400 dark:text-gray-500">
                            {formatChatTimestamp(message.timestamp)}
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <ChatMessage
                      message={message}
                      conversationId={conversationId}
                      onEdit={handleEditMessage}
                      onRegenerate={handleRegenerateResponse}
                      isGenerating={isGenerating}
                      assistantIconUrl={undefined}
                    />
                  )}
                </div>
              );
            })}

            {/* 回复时的 LoadingProgress / NetworkLoadingProgress 已隐藏，组件保留供日后 debug 使用 */}

            <div ref={messagesEndRef} />
          </div>

          {/* 输入区域 - ChatGPT风格 */}
          <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 sm:px-4 py-3 sm:py-4 flex-shrink-0 transition-colors">
            {/* Agent状态面板（深度研究模式） */}
            {deepResearchEnabled && agentStatuses.length > 0 && (
              <div className="mb-2">
                <AgentStatusPanel agents={agentStatuses} />
              </div>
            )}

            {/* 已上传文件列表 */}
            {uploadedFiles.length > 0 && (
              <div className="mb-2 space-y-2">
                {uploadedFiles.map((file) => (
                  <div
                    key={file.id}
                    className={`flex flex-col gap-1.5 px-3 py-2 rounded-lg text-xs border ${
                      file.status === "completed"
                        ? "bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border-green-200 dark:border-green-800"
                        : file.status === "failed"
                          ? "bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800"
                          : "bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <svg
                        className="w-4 h-4 flex-shrink-0"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        />
                      </svg>
                      <span className="truncate flex-1 font-medium">
                        {file.name}
                      </span>
                      {file.status === "uploading" ||
                      file.status === "processing" ? (
                        <svg
                          className="w-3.5 h-3.5 animate-spin flex-shrink-0"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                          />
                        </svg>
                      ) : file.status === "completed" ? (
                        <svg
                          className="w-3.5 h-3.5 flex-shrink-0"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      ) : file.status === "failed" ? (
                        <svg
                          className="w-3.5 h-3.5 flex-shrink-0"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M6 18L18 6M6 6l12 12"
                          />
                        </svg>
                      ) : null}
                    </div>

                    {/* 进度条和状态信息 */}
                    {(file.status === "uploading" ||
                      file.status === "processing") && (
                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-[10px]">
                          <span className="text-gray-600 dark:text-gray-400">
                            {file.status === "uploading"
                              ? "上传中"
                              : file.stage || "处理中"}
                          </span>
                          <span className="font-medium">
                            {file.progress || 0}%
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                          <div
                            className={`h-1.5 rounded-full transition-all duration-300 ${
                              file.status === "uploading"
                                ? "bg-blue-500 dark:bg-blue-400"
                                : "bg-blue-600 dark:bg-blue-500"
                            }`}
                            style={{ width: `${file.progress || 0}%` }}
                          />
                        </div>
                        {file.stageDetails && (
                          <div className="text-[10px] text-gray-500 dark:text-gray-400 italic">
                            {file.stageDetails}
                          </div>
                        )}
                      </div>
                    )}

                    {/* 状态文本 */}
                    {file.status === "completed" && (
                      <div className="text-[10px] text-green-600 dark:text-green-400">
                        处理完成，可以开始对话
                      </div>
                    )}
                    {file.status === "failed" && (
                      <div className="text-[10px] text-red-600 dark:text-red-400">
                        处理失败
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="w-full">
              {/* 输入框容器 */}
              <div className="relative border border-gray-300 dark:border-gray-600 rounded-xl sm:rounded-2xl bg-white dark:bg-gray-800 shadow-sm focus-within:ring-2 focus-within:ring-blue-500 dark:focus-within:ring-blue-400 focus-within:border-blue-500 dark:focus-within:border-blue-400 transition-all">
                {/* 文本输入区域 */}
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="给 AI 发送消息"
                  className="w-full px-3 sm:px-4 pt-2.5 sm:pt-3 pb-2 pr-10 sm:pr-12 border-0 rounded-xl sm:rounded-2xl focus:outline-none bg-transparent text-gray-800 dark:text-gray-100 resize-none text-sm sm:text-base leading-relaxed"
                  rows={1}
                  style={{
                    minHeight: "44px",
                    maxHeight: "200px",
                    height: "auto",
                  }}
                  disabled={isLoading}
                  suppressHydrationWarning
                  onInput={(e) => {
                    const target = e.target as HTMLTextAreaElement;
                    target.style.height = "auto";
                    target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
                  }}
                />

                {/* 底部工具栏 */}
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 px-3 sm:px-4 pb-2 pt-1">
                  {/* 左侧：模式切换按钮 */}
                  <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
                    {/* 深度研究模式按钮 */}
                    {deepResearchFeatureEnabled && (
                      <button
                        onClick={() => {
                          const newValue = !deepResearchEnabled;
                          setDeepResearchEnabled(newValue);
                          localStorage.setItem(
                            "deepResearchEnabled",
                            String(newValue),
                          );
                          if (newValue) {
                            setDeepResearchResults([]); // 清空之前的结果
                            setEnableRAG(false); // 深度研究模式开启时，关闭知识检索增强模式
                            localStorage.setItem("enableRAG", "false");
                          }
                        }}
                        className={`flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1.5 rounded-full text-[10px] sm:text-xs font-medium transition-all min-h-[36px] sm:min-h-0 ${
                          deepResearchEnabled
                            ? "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400"
                            : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 active:bg-gray-200 dark:active:bg-gray-600"
                        }`}
                        title="深度研究模式：多Agent协作，生成深度研究结果"
                      >
                        {/* 深度思考图标（循环/无限符号） */}
                        <svg
                          className="w-3 sm:w-3.5 h-3 sm:h-3.5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                          />
                        </svg>
                        <span className="hidden sm:inline">深度研究</span>
                        <span className="sm:hidden">深度</span>
                        {deepResearchEnabled && (
                          <span className="px-1 py-0.5 text-[9px] sm:text-[10px] font-semibold text-white bg-blue-500 rounded">
                            深研
                          </span>
                        )}
                      </button>
                    )}

                    {/* 知识库检索增强模式按钮（仅在非深度研究模式时显示） */}
                    {!deepResearchEnabled && (
                      <>
                        <button
                          onClick={() => {
                            const newValue = !enableRAG;
                            setEnableRAG(newValue);
                            localStorage.setItem("enableRAG", String(newValue));
                          }}
                          className={`flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1.5 rounded-full text-[10px] sm:text-xs font-medium transition-all min-h-[36px] sm:min-h-0 ${
                            enableRAG
                              ? "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400"
                              : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 active:bg-gray-200 dark:active:bg-gray-600"
                          }`}
                          title="知识库检索增强模式：启用后，所有消息都会进行知识库检索"
                        >
                          {/* 地球/网络图标 */}
                          <svg
                            className="w-3 sm:w-3.5 h-3 sm:h-3.5"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"
                            />
                          </svg>
                          <span className="hidden sm:inline">知识库检索</span>
                          <span className="sm:hidden">检索</span>
                        </button>
                      </>
                    )}
                  </div>

                  {/* 右侧：附件和发送按钮 */}
                  <div className="flex items-center gap-2 self-end sm:self-auto">
                    {/* 隐藏的文件输入 */}
                    <input
                      ref={fileInputRef}
                      type="file"
                      className="hidden"
                      onChange={handleFileChange}
                      accept=".pdf,.doc,.docx,.txt,.md,.pptx,.ppt"
                      disabled={uploadingFile || isLoading}
                    />
                    {/* 附件按钮 */}
                    <button
                      onClick={handleFileSelect}
                      disabled={uploadingFile || isLoading}
                      className="p-2 min-w-[44px] min-h-[44px] flex items-center justify-center text-gray-500 dark:text-gray-400 active:text-gray-700 dark:active:text-gray-200 active:bg-gray-100 dark:active:bg-gray-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title="添加附件"
                    >
                      {uploadingFile ? (
                        <svg
                          className="w-5 h-5 animate-spin"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                          />
                        </svg>
                      ) : (
                        <svg
                          className="w-5 h-5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
                          />
                        </svg>
                      )}
                    </button>
                    {/* 上传进度显示 */}
                    {uploadingFile && uploadProgress > 0 && (
                      <div className="text-xs text-gray-500 dark:text-gray-400 hidden sm:block">
                        {uploadProgress}%
                      </div>
                    )}

                    {/* 发送按钮/停止按钮 */}
                    <button
                      onClick={
                        isLoading ? handleStopGeneration : () => handleSend()
                      }
                      disabled={
                        !isLoading &&
                        (!input.trim() ||
                          uploadedFiles.some(
                            (f) =>
                              f.status === "uploading" ||
                              f.status === "processing",
                          ))
                      }
                      className={`p-2 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-lg transition-colors shadow-sm ${
                        isLoading
                          ? "bg-red-500 hover:bg-red-600 text-white"
                          : "bg-blue-500 dark:bg-blue-600 text-white active:bg-blue-600 dark:active:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
                      }`}
                      suppressHydrationWarning
                      title={
                        isLoading
                          ? "停止生成"
                          : uploadedFiles.some(
                                (f) =>
                                  f.status === "uploading" ||
                                  f.status === "processing",
                              )
                            ? "请等待附件处理完成"
                            : "发送消息"
                      }
                    >
                      {isLoading ? (
                        <svg
                          className="w-5 h-5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M6 18L18 6M6 6l12 12"
                          />
                        </svg>
                      ) : (
                        <svg
                          className="w-5 h-5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                          />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Toast 提示 */}
      <Toast
        isOpen={toast.isOpen}
        message={toast.message}
        type={toast.type}
        duration={8000}
        onClose={() => setToast({ ...toast, isOpen: false })}
      />
    </Layout>
  );
}
