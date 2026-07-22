import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  BookOpen,
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
  Search,
  X,
} from "lucide-react";

import type { ProcessingStatus, ReportCitation, ReportSection } from "@/contracts/api";
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

export function ReportWorkspace({ onOpenKnowledge }: { onOpenKnowledge: () => void }) {
  const queryClient = useQueryClient();
  const { user, logout } = useAuthStore();
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedSectionKey, setSelectedSectionKey] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<ReportCitation | null>(null);
  const [reportQuery, setReportQuery] = useState("");
  const [templateKey, setTemplateKey] = useState("");
  const [knowledgeBaseId, setKnowledgeBaseId] = useState("");
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [researchGoal, setResearchGoal] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [editorMode, setEditorMode] = useState<"edit" | "preview">("preview");
  const [notice, setNotice] = useState<string | null>(null);

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
      setNotice(`已基于历史版本创建 v${restored.current_version}`);
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
                  onClick={() => { setCreating(false); setSelectedId(item.id); setSelectedSectionKey(null); }}
                  type="button"
                >
                  <span className="line-clamp-2 text-left font-medium">{item.title}</span>
                  <span className="mt-2 flex items-center justify-between font-mono text-[10px] text-slate-400">
                    <span>{item.template_name}</span><span>v{item.current_version}</span>
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
                  <div>
                    <p className="section-label">{report.data.template_name} · {report.data.knowledge_base_name}</p>
                    <h1>{report.data.title}</h1>
                    <p className="mt-2 text-sm text-slate-500">版本 v{report.data.current_version} · 生成进度 {report.data.progress}%</p>
                  </div>
                  <button className="quiet-action" onClick={() => void api.exportReport(report.data!.id, report.data!.title)} type="button"><Download className="h-4 w-4" />导出 DOCX</button>
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
                      <div><textarea className="markdown-editor" value={draft} onChange={(event) => setDrafts((current) => ({ ...current, [selectedSection.key]: event.target.value }))} /><p className="mt-2 text-right font-mono text-[10px] text-slate-400">{saveSection.isPending ? "正在保存新版本" : "停止输入 0.9 秒后自动保存"}</p></div>
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

          <aside className="evidence-desk">
            <div><p className="section-label">引用证据</p><p className="mt-2 text-sm leading-6 text-slate-500">点击正文中的引用编号，在这里核对原始片段。</p></div>
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
              {versions.data?.slice(0, 6).map((item) => (
                <button className="history-row" key={item.id} onClick={() => report.data && restoreVersion.mutate({ reportId: report.data.id, version: item.version })} type="button">
                  <FileClock className="h-3.5 w-3.5" /><span>v{item.version} · {item.reason}</span><ChevronRight className="ml-auto h-3.5 w-3.5" />
                </button>
              ))}
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}
