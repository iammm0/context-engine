"use client";

import { useEffect, useRef, useState, memo } from "react";
import { ChatMessage as MessageType } from "@/types/chat";
import FormattedMessage from "@/components/message/FormattedMessage";
import ThinkingDots from "@/components/message/ThinkingDots";
import RAGEvaluationPanel from "@/components/chat/RAGEvaluationPanel";
import { formatChatTimestamp } from "@/lib/timezone";

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
  const messageRef = useRef<HTMLDivElement>(null);

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
                  onClick={handleSave}
                  disabled={isSaving}
                >
                  保存
                </button>
              </div>
            </div>
          ) : (
            <>
              <FormattedMessage content={message.content} />
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
                        onClick={() => setIsEditing(true)}
                      >
                        编辑
                      </button>
                    )}
                    {onRegenerate && (
                      <button
                        className="px-2 py-1 text-xs rounded bg-gray-100 text-gray-700 border border-gray-200 hover:bg-gray-200"
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
              {message.sources.slice(0, 10).map((s, idx) => (
                <li key={idx} className="truncate">
                  {
                    (s.document_title ||
                      s.document_id ||
                      s.chunk_id ||
                      "来源") as string
                  }
                  {typeof s.score === "number"
                    ? `（${s.score.toFixed(3)}）`
                    : ""}
                </li>
              ))}
            </ul>
          </div>
        )}

        {!isUser && message.evidence && message.evidence.length > 0 && (
          <details className="mt-2 w-full text-xs text-gray-600 dark:text-gray-300">
            <summary className="cursor-pointer font-semibold">检索证据</summary>
            <ul className="mt-1 space-y-1">
              {message.evidence.slice(0, 8).map((item) => (
                <li
                  key={item.id}
                  className="rounded border border-gray-200 px-2 py-1 dark:border-gray-700"
                >
                  <div className="font-medium">
                    [{item.id}]{" "}
                    {item.document_title ||
                      item.document_id ||
                      item.file_id ||
                      "证据"}
                    {typeof item.score === "number"
                      ? `（${item.score.toFixed(3)}）`
                      : ""}
                  </div>
                  <div className="line-clamp-2 text-gray-500 dark:text-gray-400">
                    {item.text}
                  </div>
                </li>
              ))}
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
