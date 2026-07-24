import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Download,
  FileClock,
  FilePenLine,
  History,
  Library,
  LoaderCircle,
  LogOut,
  Plus,
  RefreshCw,
  ScanSearch,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";

import type {
  ProcessingStatus,
  ReportCitation,
  ReportSection,
  ReportVersion,
  SimilarityResult,
} from "@/contracts/api";
import { useAuthStore } from "@/features/auth/auth-store";
import { api, ApiClientError, streamReportEvents } from "@/lib/api-client";
import { ReportAssistantSidebar } from "@/features/reports/ReportAssistantSidebar";

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
  const [similarityResult, setSimilarityResult] = useState<SimilarityResult | null>(null);
  const [leftPanel, setLeftPanel] = useState<
    "reports" | "citations" | "similarity" | "versions"
  >("reports");
  const [leftCollapsed, setLeftCollapsed] = useState(() => window.innerWidth < 1024);
  const [rightCollapsed, setRightCollapsed] = useState(() => window.innerWidth < 1024);

  useEffect(() => {
    function handleResize() {
      if (window.innerWidth < 1024) {
        setLeftCollapsed(true);
        setRightCollapsed(true);
      }
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

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
  const deleteReport = useMutation({
    mutationFn: (id: string) => api.deleteReport(id),
    onSuccess: async (_, deletedId) => {
      setNotice("报告已删除");
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      queryClient.removeQueries({ queryKey: ["report", deletedId] });
      queryClient.removeQueries({ queryKey: ["report-versions", deletedId] });
      if (selectedReportId === deletedId) {
        const remaining = reports.data?.filter((item) => item.id !== deletedId);
        if (remaining?.[0]) {
          setSelectedId(remaining[0].id);
        } else {
          setCreating(true);
        }
      }
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

        <div
          className={`report-grid report-ide-grid ${leftCollapsed ? "left-collapsed" : ""} ${rightCollapsed ? "right-collapsed" : ""}`}
        >
          <nav className="report-activity-bar" aria-label="报告工具">
            {[
              ["reports", Archive, "报告"],
              ["citations", BookOpen, "引用"],
              ["similarity", ScanSearch, "相似度"],
              ["versions", History, "版本"],
            ].map(([key, Icon, label]) => (
              <button
                className={leftPanel === key ? "active" : ""}
                key={String(key)}
                onClick={() => {
                  setLeftPanel(key as typeof leftPanel);
                  setLeftCollapsed(false);
                }}
                title={String(label)}
                type="button"
              >
                <Icon />
              </button>
            ))}
          </nav>
          <aside
            className={`report-index report-primary-sidebar ${
              leftCollapsed ? "collapsed-hidden" : ""
            }`}
          >
            <button
              className="sidebar-toggle-handle"
              onClick={() => setLeftCollapsed((value) => !value)}
              title={leftCollapsed ? "展开主侧栏" : "收起主侧栏"}
              type="button"
            >
              {leftCollapsed ? <ChevronRight /> : <ChevronLeft />}
            </button>
            {leftPanel === "reports" && (
              <>
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
                  className={`report-index-item group relative ${selectedReportId === item.id && !creating ? "active" : ""}`}
                  key={item.id}
                  onClick={() => {
                    setCreating(false);
                    setSelectedId(item.id);
                    setSelectedSectionKey(null);
                    setSelectedVersion(null);
                  }}
                  type="button"
                >
                  <span className="line-clamp-2 text-left font-medium pr-6">{item.title}</span>
                  <span className="mt-2 flex items-center justify-between font-mono text-[10px] text-slate-400">
                    <span>{item.template_name}</span><span>{item.status === "ready" ? "已完成" : "草稿/处理中"}</span><span>v{item.current_version}</span>
                    <span>{localDate(item.updated_at)}</span>
                  </span>
                  <span
                    className="absolute right-2 top-2 grid h-6 w-6 place-items-center rounded text-slate-400 opacity-0 transition-all hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
                    onClick={(event) => {
                      event.stopPropagation();
                      if (window.confirm(`确定要删除报告“${item.title}”吗？此操作不可撤销！`)) {
                        deleteReport.mutate(item.id);
                      }
                    }}
                    title="删除报告"
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.stopPropagation();
                        if (window.confirm(`确定要删除报告“${item.title}”吗？此操作不可撤销！`)) {
                          deleteReport.mutate(item.id);
                        }
                      }
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </span>
                </button>
              ))}
              {!reports.data?.length && <p className="report-empty-copy">尚未装订报告，先从两篇已归档文献开始。</p>}
            </div>
              </>
            )}
            {leftPanel === "citations" && (
              <>
                <p className="section-label">引用证据</p>
                {activeCitation ? (
                  <article className="evidence-slip">
                    <span className="citation-number">{activeCitation.marker}</span>
                    <h3>{activeCitation.document_name}</h3>
                    <blockquote>{activeCitation.content}</blockquote>
                  </article>
                ) : (
                  <p className="report-empty-copy">在预览中选择引用编号以核对原文。</p>
                )}
              </>
            )}
            {leftPanel === "similarity" && (
              <div className="similarity-container">
                <p className="section-label">相似度检测</p>
                <button
                  className="tool-primary mt-3 w-full"
                  disabled={!report.data || runSimilarity.isPending}
                  onClick={() => report.data && runSimilarity.mutate(report.data.id)}
                  type="button"
                >
                  {runSimilarity.isPending ? "正在检测..." : "检测当前报告"}
                </button>
                {similarityResult && (
                  <div className="mt-4 space-y-3">
                    <div className="similarity-summary">
                      <strong>{(similarityResult.overall_ratio * 100).toFixed(1)}%</strong>
                      <span>高相似文本占比</span>
                    </div>
                    <div className="similarity-match-list space-y-2 pt-2">
                      {similarityResult.matches.map((match) => (
                        <details
                          className="similarity-match-card rounded border border-[#b8c9ce] bg-white p-2.5 text-xs text-[#183541]"
                          key={match.id}
                        >
                          <summary className="cursor-pointer font-medium text-[#1687a0] hover:underline">
                            相似度 {(match.score * 100).toFixed(1)}% · {match.document_name}
                          </summary>
                          <div className="mt-2 space-y-1.5 pt-1 text-[11px]">
                            <p className="text-slate-500">
                              <span className="font-semibold text-slate-700">原文：</span>
                              {match.source_text}
                            </p>
                            <blockquote className="border-l-2 border-amber-500 bg-amber-50/50 p-1.5 text-amber-900">
                              <span className="font-semibold">报告匹配片段：</span>
                              {match.matched_text}
                            </blockquote>
                          </div>
                        </details>
                      ))}
                      {!similarityResult.matches.length && (
                        <p className="report-empty-copy mt-2">未发现超过阈值的高相似片段。</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
            {leftPanel === "versions" && (
              <div className="history-stack">
                <p className="section-label mb-2">版本快照</p>
                {versions.data?.map((item) => {
                  const isCurrent = item.version === report.data?.current_version;
                  const isSelected = selectedVersion?.id === item.id;
                  return (
                    <div className="history-item-block" key={item.id}>
                      <button
                        className={`history-row ${isSelected ? "active" : ""}`}
                        onClick={() =>
                          setSelectedVersion(isSelected ? null : item)
                        }
                        type="button"
                      >
                        <div className="history-row-header">
                          <div className="flex min-w-0 items-center gap-1.5">
                            <FileClock className="h-3.5 w-3.5 flex-shrink-0 text-[#1687a0]" />
                            <span className="history-title truncate font-medium">
                              v{item.version} · {versionReason(item.reason)}
                            </span>
                          </div>
                          {isCurrent && (
                            <span className="history-current-tag">当前</span>
                          )}
                        </div>
                        <div className="history-row-sub">
                          <span className="history-time">
                            {localDate(item.created_at)}
                          </span>
                        </div>
                      </button>
                      {isSelected && report.data && (
                        <div className="version-inspector-inline">
                          <div className="flex items-center justify-between gap-2 border-b border-[#c8d8dc] pb-1.5">
                            <strong className="text-xs text-[#173b49]">
                              v{selectedVersion.version} · {versionReason(selectedVersion.reason)}
                            </strong>
                            <button
                              className="quiet-action text-xs"
                              onClick={() => setSelectedVersion(null)}
                              title="关闭版本预览"
                              type="button"
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </div>
                          <p className="mt-1 text-[10px] text-slate-500">
                            恢复不会删除之后的历史，而是以这份内容建立新的当前版本。
                          </p>
                          <pre className="mt-2 max-h-36 overflow-auto border-l-2 border-[#1687a0] bg-[#f4f8f9] p-2 font-mono text-[10px] text-[#294852]">
                            {selectedVersion.content_markdown.slice(0, 700) ||
                              "该版本没有正文内容"}
                          </pre>
                          <button
                            className="version-restore-action mt-2 w-full"
                            disabled={
                              selectedVersion.version === report.data.current_version ||
                              restoreVersion.isPending
                            }
                            onClick={() =>
                              restoreVersion.mutate({
                                reportId: report.data!.id,
                                version: selectedVersion.version,
                              })
                            }
                            type="button"
                          >
                            {selectedVersion.version === report.data.current_version
                              ? "这是当前版本"
                              : restoreVersion.isPending
                                ? "正在恢复"
                                : "以此版本建立新版本"}
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
                {!versions.data?.length && (
                  <p className="report-empty-copy">暂无历史版本快照。</p>
                )}
              </div>
            )}
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
                      <div className="flex items-center gap-2">
                        <button className="compact-export" onClick={() => void exportCurrentReport()} type="button"><Download className="h-3.5 w-3.5" />校验并导出 DOCX</button>
                        <button
                          className="compact-export border-red-200 text-red-700 hover:border-red-400 hover:bg-red-50"
                          onClick={() => {
                            if (report.data && window.confirm(`确定要删除报告“${report.data.title}”吗？此操作不可撤销！`)) {
                              deleteReport.mutate(report.data.id);
                            }
                          }}
                          title="删除此报告"
                          type="button"
                        >
                          <Trash2 className="h-3.5 w-3.5 text-red-600" />删除报告
                        </button>
                      </div>
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
                              ? `已选择 ${selectedText.length} 字，可在右侧进行局部润色`
                              : "停止输入 0.9 秒后自动保存"}
                        </p>
                      </div>
                    ) : (
                      <MarkdownPreview section={selectedSection} onCitation={setSelectedCitation} />
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="report-blank"><Archive className="h-7 w-7" /><h1>选择一份报告，或建立新的装配任务。</h1></div>
            )}
          </section>

          <div
            className={`report-secondary-sidebar ${
              rightCollapsed ? "collapsed-hidden" : ""
            }`}
          >
            <button
              className="sidebar-toggle-handle secondary-toggle"
              onClick={() => setRightCollapsed((value) => !value)}
              title={rightCollapsed ? "展开 AI 副侧栏" : "收起 AI 副侧栏"}
              type="button"
            >
              {rightCollapsed ? <ChevronLeft /> : <ChevronRight />}
            </button>
            {report.data && (
              <ReportAssistantSidebar
                reportId={report.data.id}
                sectionKey={selectedSection?.key}
                selectedText={selectedText}
                onNotice={setNotice}
                onReportChanged={() => {
                  void queryClient.invalidateQueries({
                    queryKey: ["report", report.data!.id],
                  });
                  void queryClient.invalidateQueries({
                    queryKey: ["report-versions", report.data!.id],
                  });
                }}
              />
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
