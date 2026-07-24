import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  MessageSquareText,
  Pencil,
  Plus,
  Send,
  Trash2,
  WandSparkles,
} from "lucide-react";

import type {
  ChatRecord,
  PolishPreview,
  PolishStyle,
} from "@/contracts/api";
import { api, streamConversation } from "@/lib/api-client";

export function ReportAssistantSidebar({
  reportId,
  sectionKey,
  selectedText,
  onReportChanged,
  onNotice,
}: {
  reportId: string;
  sectionKey?: string;
  selectedText: string;
  onReportChanged: () => void;
  onNotice: (message: string) => void;
}) {
  const client = useQueryClient();
  const [conversationId, setConversationId] = useState("");
  const [mode, setMode] = useState("");
  const [variant, setVariant] = useState("");
  const [input, setInput] = useState("");
  const [streamed, setStreamed] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [polishPreview, setPolishPreview] = useState<PolishPreview | null>(null);

  const conversations = useQuery({
    queryKey: ["conversations", reportId],
    queryFn: () => api.listConversations(reportId),
  });
  const promptOptions = useQuery({
    queryKey: ["prompt-options"],
    queryFn: api.listPromptOptions,
  });
  const assistantOptions = useMemo(
    () =>
      (promptOptions.data ?? []).filter(
        (item) => item.key !== "report_generation" && item.variants.length > 0,
      ),
    [promptOptions.data],
  );
  const activeOption =
    assistantOptions.find((item) => item.key === mode) ?? assistantOptions[0];
  const activeMode = activeOption?.key ?? "";
  const activeVariant =
    activeOption?.variants.find((item) => item.key === variant)?.key ??
    activeOption?.variants[0]?.key ??
    "";
  const activeConversationId =
    conversationId || conversations.data?.[0]?.id || "";
  const conversation = useQuery({
    queryKey: ["conversation", activeConversationId],
    queryFn: () => api.getConversation(activeConversationId),
    enabled: Boolean(activeConversationId),
  });
  const create = useMutation({
    mutationFn: () => api.createConversation(reportId),
    onSuccess: async (item) => {
      setConversationId(item.id);
      await client.invalidateQueries({ queryKey: ["conversations", reportId] });
    },
  });
  const remove = useMutation({
    mutationFn: api.deleteConversation,
    onSuccess: async () => {
      setConversationId("");
      await client.invalidateQueries({ queryKey: ["conversations", reportId] });
    },
  });
  const previewPolish = useMutation({
    mutationFn: () =>
      api.previewPolish(reportId, {
        section_key: sectionKey!,
        text: selectedText,
        style: activeVariant as PolishStyle,
      }),
    onSuccess: setPolishPreview,
    onError: (error) => onNotice(error instanceof Error ? error.message : "润色失败"),
  });
  const acceptPolish = useMutation({
    mutationFn: (preview: PolishPreview) =>
      api.acceptPolish(reportId, {
        section_key: preview.section_key,
        text: preview.original_text,
        polished_text: preview.polished_text,
        style: preview.style,
      }),
    onSuccess: async () => {
      setPolishPreview(null);
      onReportChanged();
      onNotice("润色结果已保存为新的报告版本");
    },
  });

  const messages = useMemo(() => {
    const stored = conversation.data?.messages ?? [];
    if (!streamed) return stored;
    return [
      ...stored,
      {
        id: "streaming",
        role: "assistant",
        content: streamed,
        capability: activeMode,
        variant_key: activeVariant,
        model: null,
        usage_estimated: false,
        created_at: new Date().toISOString(),
      } satisfies ChatRecord,
    ];
  }, [
    activeMode,
    activeVariant,
    conversation.data?.messages,
    streamed,
  ]);

  async function send(event: FormEvent) {
    event.preventDefault();
    const question = input.trim();
    if (
      !question ||
      !activeConversationId ||
      !activeMode ||
      activeMode === "local_polish"
    )
      return;
    setInput("");
    setStreamed("");
    setStreaming(true);
    try {
      await streamConversation(
        activeConversationId,
        {
          question,
          capability: activeMode,
          variant_key: activeVariant,
          section_key: sectionKey,
        },
        (eventName, data) => {
          if (eventName === "delta") {
            setStreamed((current) => current + String(data.delta ?? ""));
          }
          if (eventName === "error") throw new Error(String(data.message ?? "生成失败"));
        },
      );
      setStreamed("");
      await client.invalidateQueries({
        queryKey: ["conversation", activeConversationId],
      });
      await client.invalidateQueries({ queryKey: ["conversations", reportId] });
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "对话生成失败");
    } finally {
      setStreaming(false);
    }
  }

  return (
    <aside className="assistant-sidebar">
      <header className="assistant-sidebar-head">
        <div>
          <p className="section-label">AI 副侧栏</p>
          <strong>学术协作</strong>
        </div>
        <button onClick={() => create.mutate()} title="新建对话" type="button">
          <Plus />
        </button>
      </header>
      <div className="conversation-toolbar">
        <select
          value={activeConversationId}
          onChange={(event) => setConversationId(event.target.value)}
        >
          <option value="">选择或新建对话</option>
          {conversations.data?.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
        <button
          disabled={!activeConversationId}
          onClick={async () => {
            const current = conversations.data?.find(
              (item) => item.id === activeConversationId,
            );
            if (!current) return;
            const title = window.prompt("修改对话名称", current.title);
            if (title && title.trim()) {
              try {
                await api.renameConversation(activeConversationId, title.trim());
                await client.invalidateQueries({
                  queryKey: ["conversations", reportId],
                });
              } catch (error) {
                onNotice(error instanceof Error ? error.message : "修改失败");
              }
            }
          }}
          title="修改对话名称"
          type="button"
        >
          <Pencil />
        </button>
        <button
          disabled={!activeConversationId}
          onClick={() => {
            if (window.confirm("删除当前对话？"))
              remove.mutate(activeConversationId);
          }}
          title="删除对话"
          type="button"
        >
          <Trash2 />
        </button>
      </div>

      {activeMode === "local_polish" ? (
        <div className="polish-side-panel">
          <WandSparkles />
          <p>{selectedText || "请先在主编辑器中选择需要润色的文字。"}</p>
          <button
            disabled={!sectionKey || selectedText.length < 2 || previewPolish.isPending}
            onClick={() => previewPolish.mutate()}
            type="button"
          >
            生成润色对比
          </button>
          {polishPreview && (
            <div className="polish-side-preview">
              <small>建议稿</small>
              <p>{polishPreview.polished_text}</p>
              <button
                disabled={acceptPolish.isPending}
                onClick={() => acceptPolish.mutate(polishPreview)}
                type="button"
              >
                <Check />确认并建立新版本
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="chat-transcript">
          {messages.map((item) => (
            <article className={`chat-message ${item.role}`} key={item.id}>
              <span>{item.role === "user" ? "你" : "AI"}</span>
              <p>{item.content}</p>
              {item.usage_estimated && <small>Token 用量为估算值</small>}
            </article>
          ))}
          {!messages.length && (
            <div className="chat-empty">
              <MessageSquareText />
              <p>新建对话后，可围绕当前完整报告和章节证据连续追问。</p>
            </div>
          )}
        </div>
      )}

      <form className="assistant-composer" onSubmit={send}>
        <div className="assistant-mode-row">
          <select
            disabled={!assistantOptions.length}
            value={activeMode}
            onChange={(event) => {
              const nextMode = event.target.value;
              setMode(nextMode);
              const nextOption = assistantOptions.find(
                (item) => item.key === nextMode,
              );
              setVariant(nextOption?.variants[0]?.key ?? "");
              setPolishPreview(null);
            }}
          >
            {!assistantOptions.length && <option value="">暂无已开放功能</option>}
            {assistantOptions.map((item) => (
              <option key={item.key} value={item.key}>
                {item.name}
              </option>
            ))}
          </select>
          <select
            disabled={!activeOption}
            value={activeVariant}
            onChange={(event) => setVariant(event.target.value)}
          >
            {!activeOption && <option value="">暂无已开放风格</option>}
            {activeOption?.variants.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        {activeMode && activeMode !== "local_polish" && (
          <div className="composer-input">
            <textarea
              disabled={!activeConversationId || streaming}
              placeholder={activeConversationId ? "围绕当前报告提问" : "请先新建对话"}
              rows={3}
              value={input}
              onChange={(event) => setInput(event.target.value)}
            />
            <button
              disabled={!input.trim() || !activeConversationId || streaming}
              type="submit"
            >
              <Send />
            </button>
          </div>
        )}
      </form>
      {!promptOptions.isLoading && !assistantOptions.length && (
        <p className="assistant-config-empty">
          管理员尚未开放可用的功能与风格。
        </p>
      )}
    </aside>
  );
}
