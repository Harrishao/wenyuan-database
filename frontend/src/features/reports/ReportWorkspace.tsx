import { Fragment, FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  BookOpen,
  Check,
  ChevronRight,
  Download,
  FileClock,
  FilePenLine,
  History,
  Library,
  LoaderCircle,
  LogOut,
  MessageSquareText,
  Plus,
  RefreshCw,
  ScanSearch,
  Search,
  ShieldCheck,
  WandSparkles,
  X,
} from "lucide-react";

import type {
  AssistantAnswer,
  AssistantMode,
  AssistantRole,
  PolishPreview,
  PolishStyle,
  ProcessingStatus,
  ReportCitation,
  ReportSection,
  ReportVersion,
  SimilarityResult,
} from "@/contracts/api";
import { useAuthStore } from "@/features/auth/auth-store";
import { api, ApiClientError, streamReportEvents } from "@/lib/api-client";

const sectionStatus: Record<ProcessingStatus, string> = {
  pending: "等待装订",
  running: "正在生成",
  succeeded: "已有初稿",
  failed: "生成失败",
  cancelled: "已取消",
};

function errorText(error: unknown) {
  return error instanceof ApiClientError ? error.message : "操作未完成，请检查服务状态";
}

const versionReasons: Record<string, string> = {
  initial_generation: "初次生成",
  auto_save: "编辑保存",
  generation_retry: "章节重试",
  polish_academic: "学术严谨润色",
  polish_plain: "通俗表达润色",
  polish_concise: "精简润色",
};

function versionReason(reason: string) {
  if (reason.startsWith("restore_v")) return `恢复自 v${reason.slice(9)}`;
  return versionReasons[reason] ?? reason;
}

function localDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function MarkdownPreview({
  section,
  onCitation,
}: {
  section: ReportSection;
  onCitation: (citation: ReportCitation) => void;
}) {
  const citationMap = new Map(section.citations.map((item) => [item.marker, item]));
  if (!section.content_markdown) {
    return <p className="report-empty-copy">本章节尚未形成初稿。</p>;
  }
  return (
    <div className="report-prose">
      {section.content_markdown.split(/\n{2,}/).map((block, blockIndex) => {
        const text = block.replace(/^#{1,3}\s+/, "");
        const isHeading = /^#{1,3}\s+/.test(block);
        const fragments = text.split(/(\[\d+\])/g);
        const content = fragments.map((fragment, index) => {
          const citation = citationMap.get(fragment);
          return citation ? (
            <button
              className="citation-chip"
              key={`${fragment}-${index}`}
              onClick={() => onCitation(citation)}
              type="button"
            >
              {fragment}
            </button>
          ) : (
            fragment
          );
        });
        return isHeading ? (
          <h3 key={blockIndex}>{content}</h3>
        ) : (
          <p key={blockIndex}>{content}</p>
        );
      })}
    </div>
  );
}

export function ReportWorkspace({
  onOpenKnowledge,
  onOpenAdmin,
}: {
  onOpenKnowledge: () => void;
  onOpenAdmin: () => void;
}) {
  const queryClient = useQueryClient();
  const { user, logout } = useAuthStore();
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedSectionKey, setSelectedSectionKey] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<ReportCitation | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<ReportVersion | null>(null);
  const [reportQuery, setReportQuery] = useState("");
  const [templateKey, setTemplateKey] = useState("");
  const [knowledgeBaseId, setKnowledgeBaseId] = useState("");
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [researchGoal, setResearchGoal] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [editorMode, setEditorMode] = useState<"edit" | "preview">("preview");
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedText, setSelectedText] = useState("");
  const [polishStyle, setPolishStyle] = useState<PolishStyle>("academic");
  const [polishPreview, setPolishPreview] = useState<PolishPreview | null>(null);
  const [similarityResult, setSimilarityResult] = useState<SimilarityResult | null>(null);
  const [assistantRole, setAssistantRole] = useState<AssistantRole>("rigorous_mentor");
  const [assistantMode, setAssistantMode] = useState<AssistantMode>("dialogue");
  const [assistantQuestion, setAssistantQuestion] = useState("");
  const [assistantAnswer, setAssistantAnswer] = useState<AssistantAnswer | null>(null);

  const templates = useQuery({ queryKey: ["report-templates"], queryFn: api.listReportTemplates });
  const knowledgeBases = useQuery({ queryKey: ["knowledge-bases"], queryFn: api.listKnowledgeBases });
  const reports = useQuery({
    queryKey: ["reports", reportQuery],
    queryFn: () => api.listReports(reportQuery),
  });
  const selectedReportId =
    selectedId ?? (creating ? null : reports.data?.[0]?.id ?? null);
  const report = useQuery({
    queryKey: ["report", selectedReportId],
    queryFn: () => api.getReport(selectedReportId!),
    enabled: Boolean(selectedReportId),
  });
  const versions = useQuery({
    queryKey: ["report-versions", selectedReportId],
    queryFn: () => api.listReportVersions(selectedReportId!),
    enabled: Boolean(selectedReportId),
  });
  const selectedSection = useMemo(
    () =>
      report.data?.sections.find((item) => item.key === selectedSectionKey) ??
      report.data?.sections[0],
    [report.data, selectedSectionKey],
  );
  const draft = selectedSection
    ? (drafts[selectedSection.key] ?? selectedSection.content_markdown)
    : "";
  const activeCitation = selectedCitation ?? selectedSection?.citations[0] ?? null;

  async function exportCurrentReport() {
    if (!report.data) return;
    try {
      const integrity = await api.checkCitationIntegrity(report.data.id);
      if (!integrity.valid) {
        setNotice(`导出前检查：${integrity.warnings.join("；")}`);
        return;
      }
      await api.exportReport(report.data.id, report.data.title);
      setNotice("DOCX 已导出，正文引用与文末参考文献已核对");
    } catch (error) {
      setNotice(errorText(error));
    }
  }
  const reportStatus = report.data?.status;

  useEffect(() => {
    if (!selectedReportId || !reportStatus || !["draft", "generating"].includes(reportStatus)) {
      return;
    }
    const controller = new AbortController();
    void streamReportEvents(
      selectedReportId,
      () => {
        void queryClient.invalidateQueries({ queryKey: ["report", selectedReportId] });
        void queryClient.invalidateQueries({ queryKey: ["reports"] });
      },
      controller.signal,
    ).catch((error: unknown) => {
      if (!controller.signal.aborted) setNotice(errorText(error));
    });
    return () => controller.abort();
  }, [queryClient, reportStatus, selectedReportId]);

  const createReport = useMutation({
    mutationFn: api.createReport,
    onSuccess: async ({ report: created }) => {
      setSelectedId(created.id);
      setCreating(false);
      setSelectedSectionKey(created.sections[0]?.key ?? null);
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      queryClient.setQueryData(["report", created.id], created);
      setNotice("报告已进入分章节生成队列");
    },
    onError: (error) => setNotice(errorText(error)),
  });
  const saveSection = useMutation({
    mutationFn: (payload: { reportId: string; sectionKey: string; content: string }) =>
      api.updateReportSection(payload.reportId, payload.sectionKey, payload.content),
    onSuccess: async (saved) => {
      queryClient.setQueryData(["report", saved.id], saved);
      await queryClient.invalidateQueries({ queryKey: ["report-versions", saved.id] });
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: (error) => setNotice(errorText(error)),
  });
  const retrySection = useMutation({
    mutationFn: ({ reportId, sectionKey }: { reportId: string; sectionKey: string }) =>
      api.retryReportSection(reportId, sectionKey),
    onSuccess: ({ report: updated }) => {
      queryClient.setQueryData(["report", updated.id], updated);
      setNotice("当前章节已重新进入生成队列");
    },
    onError: (error) => setNotice(errorText(error)),
  });
  const restoreVersion = useMutation({
    mutationFn: ({ reportId, version }: { reportId: string; version: number }) =>
      api.restoreReportVersion(reportId, version),
    onSuccess: async (restored) => {
      queryClient.setQueryData(["report", restored.id], restored);
      await queryClient.invalidateQueries({ queryKey: ["report-versions", restored.id] });
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      setDrafts({});
      setSelectedCitation(null);
      setSelectedVersion(null);
      setNotice(`已基于历史版本创建 v${restored.current_version}`);
    },
    onError: (error) => setNotice(errorText(error)),
  });
  const runSimilarity = useMutation({
    mutationFn: (reportId: string) => api.runSimilarity(reportId),
    onSuccess: (result) => {
      setSimilarityResult(result);
      setNotice(`检测完成：发现 ${result.matches.length} 个高相似片段`);
    },
    onError: (error) => setNotice(errorText(error)),
  });
  const previewPolish = useMutation({
    mutationFn: (payload: {
      reportId: string;
      sectionKey: string;
      text: string;
      style: PolishStyle;
    }) =>
      api.previewPolish(payload.reportId, {
        section_key: payload.sectionKey,
        text: payload.text,
        style: payload.style,
      }),
    onSuccess: setPolishPreview,
    onError: (error) => setNotice(errorText(error)),
  });
  const acceptPolish = useMutation({
    mutationFn: (payload: { reportId: string; preview: PolishPreview }) =>
      api.acceptPolish(payload.reportId, {
        section_key: payload.preview.section_key,
        text: payload.preview.original_text,
        polished_text: payload.preview.polished_text,
        style: payload.preview.style,
      }),
    onSuccess: async (updated) => {
      queryClient.setQueryData(["report", updated.id], updated);
      await queryClient.invalidateQueries({ queryKey: ["report-versions", updated.id] });
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      setDrafts({});
      setSelectedText("");
      setPolishPreview(null);
      setNotice(`润色已确认并保存为 v${updated.current_version}`);
    },
    onError: (error) => setNotice(errorText(error)),
  });
  const askAssistant = useMutation({
    mutationFn: (payload: {
      reportId: string;
      role: AssistantRole;
      mode: AssistantMode;
      question: string;
      sectionKey?: string;
    }) =>
      api.askAssistant(payload.reportId, {
        role: payload.role,
        mode: payload.mode,
        question: payload.question,
        section_key: payload.sectionKey,
      }),
    onSuccess: setAssistantAnswer,
    onError: (error) => setNotice(errorText(error)),
  });

  useEffect(() => {
    if (
      editorMode !== "edit" ||
      !report.data ||
      !selectedSection ||
      draft === selectedSection.content_markdown ||
      saveSection.isPending
    ) {
      return;
    }
    const timer = window.setTimeout(() => {
      saveSection.mutate({
        reportId: report.data.id,
        sectionKey: selectedSection.key,
        content: draft,
      });
    }, 900);
    return () => window.clearTimeout(timer);
  }, [draft, editorMode, report.data, saveSection, selectedSection]);

  function submitReport(event: FormEvent) {
    event.preventDefault();
    if (!templateKey || !knowledgeBaseId) return;
    createReport.mutate({
      knowledge_base_id: knowledgeBaseId,
      template_key: templateKey,
      title,
      inputs: { topic, research_goal: researchGoal },
    });
  }

  function beginCreating() {
    setCreating(true);
    setSelectedId(null);
    setTemplateKey(templates.data?.[0]?.key ?? "");
    setKnowledgeBaseId(knowledgeBases.data?.[0]?.id ?? "");
  }

  return (
    <main className="min-h-screen bg-[#e8eef1] p-3 text-[#183541] sm:p-5">
      <div className="report-shell mx-auto min-h-[calc(100vh-1.5rem)] max-w-[1700px] sm:min-h-[calc(100vh-2.5rem)]">
        <header className="report-topbar">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center bg-[#173b49] text-white">
              <FilePenLine className="h-4 w-4" />
            </span>
            <div>
              <p className="font-serif text-xl font-semibold tracking-[0.16em]">报告装配台</p>
              <p className="font-mono text-[10px] tracking-[0.16em] text-slate-400">EVIDENCE-BOUND DRAFTING</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <button className="quiet-action" onClick={onOpenKnowledge} type="button">
              <Library className="h-4 w-4" />返回知识库
            </button>
            {user?.role === "admin" && (
              <button className="quiet-action" onClick={onOpenAdmin} type="button">
                <ShieldCheck className="h-4 w-4" />管理控制台
              </button>
            )}
            <span className="hidden text-slate-500 md:inline">{user?.display_name}</span>
            <button className="quiet-action" onClick={() => void logout()} type="button">
              <LogOut className="h-4 w-4" />退出
            </button>
          </div>
        </header>

        {notice && (
          <button className="report-notice" onClick={() => setNotice(null)} type="button">
            <span>{notice}</span><X className="h-3.5 w-3.5" />
          </button>
        )}

        <div className="report-grid">
          <aside className="report-index">
            <div className="flex items-center justify-between">
              <div><p className="section-label">报告卷宗</p><p className="mt-1 text-xs text-slate-400">按标题或模板检索</p></div>
              <button className="icon-button" onClick={beginCreating} title="新建报告" type="button">
                <Plus className="h-4 w-4" />
              </button>
            </div>
            <label className="archive-search mt-4">
              <Search className="h-4 w-4 text-slate-400" />
              <input value={reportQuery} onChange={(event) => setReportQuery(event.target.value)} placeholder="检索历史报告" />
            </label>
            <div className="mt-5 space-y-1">
              {reports.data?.map((item) => (
                <button
                  className={`report-index-item ${selectedReportId === item.id && !creating ? "active" : ""}`}
                  key={item.id}
                  onClick={() => {
                    setCreating(false);
                    setSelectedId(item.id);
                    setSelectedSectionKey(null);
                    setSelectedVersion(null);
                  }}
                  type="button"
                >
                  <span className="line-clamp-2 text-left font-medium">{item.title}</span>
                  <span className="mt-2 flex items-center justify-between font-mono text-[10px] text-slate-400">
                    <span>{item.template_name}</span><span>{item.status === "ready" ? "已完成" : "草稿/处理中"}</span><span>v{item.current_version}</span>
                    <span>{localDate(item.updated_at)}</span>
                  </span>
                </button>
              ))}
              {!reports.data?.length && <p className="report-empty-copy">尚未装订报告，先从两篇已归档文献开始。</p>}
            </div>
          </aside>

          <section className="report-stage">
            {creating ? (
              <form className="report-create-sheet" onSubmit={submitReport}>
                <p className="section-label">新建报告任务</p>
                <h1>先确定装订规则，再让证据进入章节。</h1>
                <div className="report-form-grid">
                  <label><span>报告标题</span><input value={title} onChange={(event) => setTitle(event.target.value)} required minLength={2} /></label>
                  <label><span>报告模板</span><select value={templateKey} onChange={(event) => setTemplateKey(event.target.value)} required><option value="">选择模板</option>{templates.data?.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}</select></label>
                  <label><span>证据知识库</span><select value={knowledgeBaseId} onChange={(event) => setKnowledgeBaseId(event.target.value)} required><option value="">选择知识库</option>{knowledgeBases.data?.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.document_count} 篇</option>)}</select></label>
                  <label><span>研究主题</span><input value={topic} onChange={(event) => setTopic(event.target.value)} required /></label>
                  <label className="wide"><span>研究目标</span><textarea value={researchGoal} onChange={(event) => setResearchGoal(event.target.value)} required rows={4} /></label>
                </div>
                <div className="mt-6 flex gap-3">
                  <button className="primary-action" disabled={createReport.isPending} type="submit">{createReport.isPending ? "正在建立任务" : "生成分章节初稿"}</button>
                  <button className="quiet-action" onClick={() => setCreating(false)} type="button">取消</button>
                </div>
              </form>
            ) : report.data ? (
              <>
                <div className="report-heading">
                  <div className="min-w-0 flex-1">
                    <div className="report-kicker-row">
                      <p className="section-label">{report.data.template_name} · {report.data.knowledge_base_name}</p>
                      <button className="compact-export" onClick={() => void exportCurrentReport()} type="button"><Download className="h-3.5 w-3.5" />校验并导出 DOCX</button>
                    </div>
                    <h1>{report.data.title}</h1>
                    <p className="mt-2 text-sm text-slate-500">版本 v{report.data.current_version} · 生成进度 {report.data.progress}%</p>
                    {report.data.moderation_status !== "approved" && (
                      <p className="mt-2 border-l-2 border-amber-600 pl-3 text-sm text-amber-800">
                        内容审核状态：{report.data.moderation_status}
                        {report.data.moderation_note ? ` · ${report.data.moderation_note}` : ""}
                      </p>
                    )}
                  </div>
                </div>
                <div className="assembly-line" style={{ "--report-progress": `${report.data.progress}%` } as React.CSSProperties} />
                <div className="section-binding" aria-label="报告章节">
                  {report.data.sections.map((section) => (
                    <button
                      className={`binding-tab status-${section.status} ${selectedSection?.key === section.key ? "active" : ""}`}
                      key={section.key}
                      onClick={() => { setSelectedSectionKey(section.key); setSelectedCitation(null); }}
                      type="button"
                    >
                      <span>{String(section.position).padStart(2, "0")}</span>
                      <strong>{section.title}</strong>
                      <small>{sectionStatus[section.status]}</small>
                    </button>
                  ))}
                </div>
                {selectedSection && (
                  <div className="chapter-desk">
                    <div className="chapter-toolbar">
                      <div><p className="section-label">章节 {String(selectedSection.position).padStart(2, "0")}</p><h2>{selectedSection.title}</h2></div>
                      <div className="flex gap-2">
                        <button className={`mode-button ${editorMode === "edit" ? "active" : ""}`} onClick={() => setEditorMode("edit")} type="button">编辑</button>
                        <button className={`mode-button ${editorMode === "preview" ? "active" : ""}`} onClick={() => setEditorMode("preview")} type="button">预览</button>
                        <button className="icon-button" onClick={() => retrySection.mutate({ reportId: report.data!.id, sectionKey: selectedSection.key })} title="只重新生成本章节" type="button"><RefreshCw className="h-4 w-4" /></button>
                      </div>
                    </div>
                    {selectedSection.status === "running" ? (
                      <div className="report-generating"><LoaderCircle className="h-5 w-5 animate-spin" />正在检索证据并生成本章节</div>
                    ) : editorMode === "edit" ? (
                      <div>
                        <textarea
                          className="markdown-editor"
                          value={draft}
                          onChange={(event) =>
                            setDrafts((current) => ({
                              ...current,
                              [selectedSection.key]: event.target.value,
                            }))
                          }
                          onSelect={(event) => {
                            const target = event.currentTarget;
                            setSelectedText(
                              target.value.slice(target.selectionStart, target.selectionEnd).trim(),
                            );
                          }}
                        />
                        <p className="mt-2 text-right font-mono text-[10px] text-slate-400">
                          {saveSection.isPending
                            ? "正在保存新版本"
                            : selectedText
                              ? `已选择 ${selectedText.length} 字，可在下方润色`
                              : "停止输入 0.9 秒后自动保存"}
                        </p>
                      </div>
                    ) : (
                      <MarkdownPreview section={selectedSection} onCitation={setSelectedCitation} />
                    )}
                  </div>
                )}
                {selectedSection && (
                  <div className="academic-tool-grid">
                    <section className="academic-tool-card">
                      <div className="academic-tool-heading">
                        <ScanSearch className="h-4 w-4" />
                        <div>
                          <p className="section-label">私有语料相似度检测</p>
                          <small>字符 2–4 gram TF-IDF · 余弦相似度</small>
                        </div>
                      </div>
                      <button
                        className="tool-primary"
                        disabled={runSimilarity.isPending}
                        onClick={() => runSimilarity.mutate(report.data!.id)}
                        type="button"
                      >
                        {runSimilarity.isPending ? "正在逐句比对" : "检测当前报告"}
                      </button>
                      {similarityResult && (
                        <div className="similarity-summary">
                          <strong>
                            {(similarityResult.overall_ratio * 100).toFixed(1)}%
                          </strong>
                          <span>{similarityResult.metric_label}，不是权威平台查重率</span>
                          <div className="similarity-match-list">
                            {similarityResult.matches.slice(0, 5).map((match) => (
                              <details key={match.id}>
                                <summary>
                                  相似度 {(match.score * 100).toFixed(1)}% · {match.document_name}
                                </summary>
                                <p className="similarity-source">{match.source_text}</p>
                                <blockquote>{match.matched_text}</blockquote>
                              </details>
                            ))}
                            {!similarityResult.matches.length && (
                              <p className="report-empty-copy">未发现超过阈值的片段。</p>
                            )}
                          </div>
                        </div>
                      )}
                    </section>

                    <section className="academic-tool-card">
                      <div className="academic-tool-heading">
                        <WandSparkles className="h-4 w-4" />
                        <div>
                          <p className="section-label">定向润色</p>
                          <small>先预览，确认后才建立新版本</small>
                        </div>
                      </div>
                      <select
                        value={polishStyle}
                        onChange={(event) => setPolishStyle(event.target.value as PolishStyle)}
                      >
                        <option value="academic">学术严谨</option>
                        <option value="plain">通俗表达</option>
                        <option value="concise">精简</option>
                      </select>
                      <textarea
                        className="tool-textarea"
                        onChange={(event) => setSelectedText(event.target.value)}
                        placeholder="在章节编辑器中选中文字，或在此粘贴待润色片段"
                        rows={4}
                        value={selectedText}
                      />
                      <button
                        className="tool-primary"
                        disabled={selectedText.length < 2 || previewPolish.isPending}
                        onClick={() =>
                          previewPolish.mutate({
                            reportId: report.data!.id,
                            sectionKey: selectedSection.key,
                            text: selectedText,
                            style: polishStyle,
                          })
                        }
                        type="button"
                      >
                        {previewPolish.isPending ? "正在生成预览" : "生成前后对比"}
                      </button>
                      {polishPreview && (
                        <div className="polish-comparison">
                          <div><span>原文</span><p>{polishPreview.original_text}</p></div>
                          <div><span>建议稿</span><p>{polishPreview.polished_text}</p></div>
                          <button
                            className="tool-confirm"
                            disabled={acceptPolish.isPending}
                            onClick={() =>
                              acceptPolish.mutate({
                                reportId: report.data!.id,
                                preview: polishPreview,
                              })
                            }
                            type="button"
                          >
                            <Check className="h-3.5 w-3.5" />
                            {acceptPolish.isPending ? "正在建立版本" : "确认并保存新版本"}
                          </button>
                        </div>
                      )}
                    </section>

                    <section className="academic-tool-card">
                      <div className="academic-tool-heading">
                        <MessageSquareText className="h-4 w-4" />
                        <div>
                          <p className="section-label">证据型学术助手</p>
                          <small>回答仅引用当前私有知识库</small>
                        </div>
                      </div>
                      <div className="tool-select-row">
                        <select
                          value={assistantRole}
                          onChange={(event) =>
                            setAssistantRole(event.target.value as AssistantRole)
                          }
                        >
                          <option value="rigorous_mentor">严谨导师</option>
                          <option value="data_analyst">数据分析专家</option>
                        </select>
                        <select
                          value={assistantMode}
                          onChange={(event) =>
                            setAssistantMode(event.target.value as AssistantMode)
                          }
                        >
                          <option value="dialogue">普通对话</option>
                          <option value="revision">修改建议</option>
                        </select>
                      </div>
                      <textarea
                        className="tool-textarea"
                        onChange={(event) => setAssistantQuestion(event.target.value)}
                        placeholder="例如：本章节的论证还缺少哪些可验证指标？"
                        rows={4}
                        value={assistantQuestion}
                      />
                      <button
                        className="tool-primary"
                        disabled={assistantQuestion.length < 2 || askAssistant.isPending}
                        onClick={() =>
                          askAssistant.mutate({
                            reportId: report.data!.id,
                            role: assistantRole,
                            mode: assistantMode,
                            question: assistantQuestion,
                            sectionKey: selectedSection.key,
                          })
                        }
                        type="button"
                      >
                        {askAssistant.isPending ? "正在检索证据" : "向当前角色提问"}
                      </button>
                      {assistantAnswer && (
                        <div className="assistant-answer">
                          <p>{assistantAnswer.answer}</p>
                          {assistantAnswer.evidence.map((item) => (
                            <small key={item.document_chunk_id}>
                              {item.marker} {item.document_name}
                            </small>
                          ))}
                        </div>
                      )}
                    </section>
                  </div>
                )}
              </>
            ) : (
              <div className="report-blank"><Archive className="h-7 w-7" /><h1>选择一份报告，或建立新的装配任务。</h1></div>
            )}
          </section>

          <aside className="evidence-desk">
            <div><p className="section-label">引用证据</p><p className="mt-2 text-sm leading-6 text-slate-500">点击预览中的引用编号，在这里核对原始片段。</p></div>
            {activeCitation ? (
              <article className="evidence-slip">
                <div className="flex items-center justify-between"><span className="citation-number">{activeCitation.marker}</span><BookOpen className="h-4 w-4 text-[#1687a0]" /></div>
                <h3>{activeCitation.document_name}</h3>
                <p className="font-mono text-[10px] text-slate-400">{activeCitation.heading || "正文"}{activeCitation.page_number ? ` · 第 ${activeCitation.page_number} 页` : ""}</p>
                <blockquote>{activeCitation.content}</blockquote>
              </article>
            ) : (
              <p className="report-empty-copy">当前章节还没有可核对的引用。</p>
            )}
            <div className="history-stack">
              <div className="flex items-center gap-2"><History className="h-4 w-4" /><p className="section-label">版本快照</p></div>
              {versions.data?.slice(0, 6).map((item, index, items) => (
                <Fragment key={item.id}>
                  {(index === 0 ||
                    new Date(items[index - 1].created_at).toLocaleDateString() !==
                      new Date(item.created_at).toLocaleDateString()) && (
                    <p className="mt-3 text-xs font-medium text-slate-400">
                      {new Date(item.created_at).toLocaleDateString()}
                    </p>
                  )}
                  <button
                    className={`history-row ${selectedVersion?.id === item.id ? "active" : ""}`}
                    onClick={() => setSelectedVersion(item)}
                    type="button"
                  >
                    <FileClock className="h-3.5 w-3.5 flex-shrink-0" />
                    <span className="history-title">
                      v{item.version} · {versionReason(item.reason)}
                    </span>
                    <small className="history-time">
                      {localDate(item.created_at)}
                    </small>
                    <div className="history-badge">
                      {item.version === report.data?.current_version ? (
                        <small>当前</small>
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5" />
                      )}
                    </div>
                  </button>
                </Fragment>
              ))}
              {selectedVersion && report.data && (
                <div className="version-inspector">
                  <div className="flex items-center justify-between gap-3">
                    <strong>v{selectedVersion.version} · {versionReason(selectedVersion.reason)}</strong>
                    <button className="icon-button" onClick={() => setSelectedVersion(null)} title="关闭版本预览" type="button"><X className="h-3.5 w-3.5" /></button>
                  </div>
                  <p>恢复不会删除之后的历史，而是以这份内容建立新的当前版本。</p>
                  <pre>{selectedVersion.content_markdown.slice(0, 700) || "该版本没有正文内容"}</pre>
                  <button
                    className="version-restore-action"
                    disabled={selectedVersion.version === report.data.current_version || restoreVersion.isPending}
                    onClick={() => restoreVersion.mutate({ reportId: report.data!.id, version: selectedVersion.version })}
                    type="button"
                  >
                    {selectedVersion.version === report.data.current_version ? "这是当前版本" : restoreVersion.isPending ? "正在恢复" : "以此内容建立新版本"}
                  </button>
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}
