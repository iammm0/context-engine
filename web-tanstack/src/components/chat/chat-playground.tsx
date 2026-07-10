import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Bot, Cpu, FileSearch, SendHorizontal, Sparkles, User } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { useUiStore } from "@/stores/ui-store"
import type { ChatStreamEvent, ConversationDetail } from "@/types/api"

function formatTime(value?: string | null) {
  if (!value) {
    return "刚刚"
  }

  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}

export function ChatPlayground() {
  const queryClient = useQueryClient()
  const { activeConversationId, setActiveConversationId, selectedKnowledgeSpaceId, enableRag, setEnableRag } =
    useUiStore()
  const [prompt, setPrompt] = useState("")
  const [draftAnswer, setDraftAnswer] = useState("")
  const [streamingMeta, setStreamingMeta] = useState<{ sources: number; status: string }>({
    sources: 0,
    status: "Idle",
  })
  const messageListRef = useRef<HTMLDivElement>(null)

  const conversationsQuery = useQuery({
    queryKey: ["conversations"],
    queryFn: async () => {
      const result = await api.getConversations()
      if (result.error) {
        throw new Error(result.error)
      }
      return result.data
    },
  })

  const conversationDetailQuery = useQuery({
    queryKey: ["conversation", activeConversationId],
    enabled: Boolean(activeConversationId),
    queryFn: async () => {
      const result = await api.getConversation(activeConversationId!)
      if (result.error) {
        throw new Error(result.error)
      }
      return result.data
    },
  })

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const result = await api.getModels()
      if (result.error) {
        throw new Error(result.error)
      }
      return result.data
    },
  })

  useEffect(() => {
    if (!activeConversationId && conversationsQuery.data?.conversations?.length) {
      setActiveConversationId(conversationsQuery.data.conversations[0].id)
    }
  }, [activeConversationId, conversationsQuery.data, setActiveConversationId])

  useEffect(() => {
    if (!messageListRef.current) {
      return
    }

    messageListRef.current.scrollTop = messageListRef.current.scrollHeight
  }, [conversationDetailQuery.data, draftAnswer])

  const createConversationMutation = useMutation({
    mutationFn: async () => {
      const result = await api.createConversation("TanStack 新对话")
      if (result.error || !result.data) {
        throw new Error(result.error || "创建对话失败")
      }
      return result.data
    },
    onSuccess: async (data) => {
      setActiveConversationId(data.id)
      await queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  const sendMutation = useMutation({
    mutationFn: async (question: string) => {
      let conversationId = activeConversationId

      if (!conversationId) {
        const created = await createConversationMutation.mutateAsync()
        conversationId = created.id
      }

      const currentConversation =
        queryClient.getQueryData<ConversationDetail>(["conversation", conversationId]) ||
        conversationDetailQuery.data ||
        ({
          id: conversationId,
          title: "TanStack 新对话",
          messages: [],
        } satisfies ConversationDetail)

      queryClient.setQueryData(["conversation", conversationId], {
        ...currentConversation,
        messages: [
          ...(currentConversation.messages || []),
          {
            role: "user",
            content: question,
            timestamp: new Date().toISOString(),
          },
        ],
      })

      await api.addConversationMessage(conversationId, {
        role: "user",
        content: question,
      })

      setDraftAnswer("")
      setStreamingMeta({ sources: 0, status: "Streaming" })
      let assistantText = ""
      let finalEvent: ChatStreamEvent | undefined

      await api.streamChat(
        {
          query: question,
          conversation_id: conversationId,
          knowledge_space_ids: selectedKnowledgeSpaceId ? [selectedKnowledgeSpaceId] : undefined,
          enable_rag: enableRag,
          generation_config: {
            llm_model: modelsQuery.data?.models?.[0]?.name,
          },
        },
        (event) => {
          finalEvent = event.done ? event : finalEvent

          if (event.error) {
            setDraftAnswer(`请求失败：${event.error}`)
            setStreamingMeta({ sources: 0, status: "Error" })
            return
          }

          if (event.content) {
            assistantText += event.content
            setDraftAnswer(assistantText)
          }

          if (event.done) {
            queryClient.setQueryData(["conversation", conversationId], (existing: ConversationDetail | undefined) => ({
              ...(existing || currentConversation),
              messages: [
                ...(existing?.messages || currentConversation.messages || []),
                {
                  role: "assistant",
                  content: assistantText,
                  timestamp: new Date().toISOString(),
                  sources: event.sources,
                  recommended_resources: event.recommended_resources,
                },
              ],
            }))
            setStreamingMeta({ sources: event.sources?.length || 0, status: "Done" })
          }
        },
      )

      if (assistantText.trim()) {
        await api.addConversationMessage(conversationId, {
          role: "assistant",
          content: assistantText,
          sources: finalEvent?.sources,
          recommended_resources: finalEvent?.recommended_resources,
        })
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["conversations"] }),
        queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] }),
      ])
    },
  })

  const messages = conversationDetailQuery.data?.messages || []
  const errors = [
    conversationsQuery.error instanceof Error ? `会话列表加载失败：${conversationsQuery.error.message}` : null,
    conversationDetailQuery.error instanceof Error ? `会话详情加载失败：${conversationDetailQuery.error.message}` : null,
    modelsQuery.error instanceof Error ? `模型列表加载失败：${modelsQuery.error.message}` : null,
    sendMutation.error instanceof Error ? `消息发送失败：${sendMutation.error.message}` : null,
  ].filter(Boolean) as string[]

  const allMessages =
    draftAnswer.trim().length > 0
      ? [
          ...messages,
          {
            role: "assistant" as const,
            content: draftAnswer,
            timestamp: new Date().toISOString(),
          },
        ]
      : messages

  return (
    <div className="grid gap-5 xl:grid-cols-[340px_minmax(0,1fr)]">
      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle>Conversation Stack</CardTitle>
          <CardDescription>TanStack Query 管理列表与详情缓存，Zustand 保存当前会话与 RAG 开关。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button
            className="w-full"
            onClick={() => createConversationMutation.mutate()}
            variant="secondary"
          >
            <Sparkles className="size-4" />
            新建会话
          </Button>

          <div className="space-y-2">
            {(conversationsQuery.data?.conversations || []).map((conversation) => (
              <button
                key={conversation.id}
                className={`w-full rounded-2xl border p-3 text-left transition-all focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-sky-100 ${
                  activeConversationId === conversation.id
                    ? "border-sky-950 bg-sky-950 text-white shadow-[0_12px_24px_rgba(12,74,110,0.16)]"
                    : "border-[var(--blue-line)] bg-white text-slate-700 hover:bg-[var(--surface-blue)] hover:text-sky-950"
                }`}
                onClick={() => setActiveConversationId(conversation.id)}
                type="button"
              >
                <div className="truncate text-sm font-medium">{conversation.title}</div>
                <div className="mt-1 text-xs opacity-70">{conversation.message_count} messages</div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4">
        <Card>
          <CardHeader className="pb-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle>Streaming Chat</CardTitle>
                <CardDescription>直接对接 `/api/chat` SSE，作为 TanStack 版聊天主工作区。</CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge>{streamingMeta.status}</Badge>
                <Badge>sources {streamingMeta.sources}</Badge>
                <Badge>{enableRag ? "RAG on" : "RAG off"}</Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {errors.length > 0 ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {errors.map((error) => (
                  <div key={error}>{error}</div>
                ))}
              </div>
            ) : null}

            <div
              className="blue-panel h-[440px] space-y-4 overflow-y-auto rounded-2xl p-4"
              ref={messageListRef}
            >
              {allMessages.length === 0 ? (
                <div className="flex h-full items-center justify-center text-center text-slate-500">
                  发一条消息试试，右侧文档面板选择知识空间后可以直接走 RAG 检索。
                </div>
              ) : (
                allMessages.map((message, index) => (
                  <div
                    key={`${message.role}-${index}-${message.timestamp}`}
                    className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    {message.role === "assistant" && (
                      <div className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-sky-100 text-sky-900">
                        <Bot className="size-4" />
                      </div>
                    )}
                    <div
                      className={`max-w-[80%] rounded-[1.6rem] px-4 py-3 text-sm leading-6 ${
                        message.role === "user"
                          ? "bg-sky-950 text-white shadow-[0_12px_28px_rgba(12,74,110,0.16)]"
                          : "border border-[var(--blue-line)] bg-white text-slate-800"
                      }`}
                    >
                      <div className="whitespace-pre-wrap">{message.content}</div>
                      <div className="mt-2 flex items-center gap-2 text-[11px] opacity-60">
                        {message.role === "user" ? <User className="size-3" /> : <Cpu className="size-3" />}
                        <span>{formatTime(message.timestamp)}</span>
                        {message.sources?.length ? <span>{message.sources.length} sources</span> : null}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            <Separator />

            <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
              <Textarea
                placeholder="输入问题，例如：请基于当前知识空间总结上下文引擎的检索链路，并指出可优化点。"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                className="min-h-[144px]"
              />
              <div className="flex flex-col justify-between gap-3 lg:w-[240px]">
                <label className="blue-panel flex cursor-pointer items-center justify-between rounded-2xl px-4 py-3">
                  <div>
                    <div className="text-sm font-medium text-slate-950">RAG retrieval</div>
                    <div className="text-xs text-slate-500">知识空间增强问答</div>
                  </div>
                  <input
                    checked={enableRag}
                    className="size-4 accent-sky-700"
                    onChange={(event) => setEnableRag(event.target.checked)}
                    type="checkbox"
                  />
                </label>

                <div className="space-y-2 rounded-2xl border border-[var(--blue-line)] bg-white p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Active model</div>
                  <div className="text-sm font-medium text-slate-900">
                    {modelsQuery.data?.models?.[0]?.name ||
                      (modelsQuery.isError ? "Model unavailable" : "Loading models...")}
                  </div>
                  <div className="text-xs leading-5 text-slate-500">
                    这里可以继续扩展多模型切换、Embedding 选择和深度研究入口。
                  </div>
                </div>

                <Button
                  className="h-14 rounded-2xl"
                  disabled={!prompt.trim() || sendMutation.isPending}
                  onClick={() => {
                    void sendMutation.mutateAsync(prompt)
                    setPrompt("")
                  }}
                  size="lg"
                >
                  <SendHorizontal className="size-4" />
                  发送消息
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Chat Notes</CardTitle>
            <CardDescription>当前实现优先打通数据链路，后面可以继续补深度研究可视化、消息编辑与中断控制。</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Badge>TanStack Router page</Badge>
            <Badge className="bg-white text-slate-700">TanStack Query cache</Badge>
            <Badge className="bg-white text-slate-700">SSE stream parser</Badge>
            <Badge className="bg-white text-slate-700">Zustand state</Badge>
            <Badge>
              <FileSearch className="mr-1 size-3" />
              backend-compatible
            </Badge>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
