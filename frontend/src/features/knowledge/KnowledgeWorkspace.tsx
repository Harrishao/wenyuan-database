import { FormEvent, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  ChevronRight,
  FileSearch,
  FileText,
  LogOut,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import type { DocumentRecord, ProcessingStatus, SearchResponse } from "@/contracts/api";
import { useAuthStore } from "@/features/auth/auth-store";
import { api, ApiClientError } from "@/lib/api-client";

const statusLabels: Record<ProcessingStatus, string> = {
  pending: "等待归档",
  running: "正在解析",
  succeeded: "可以检索",
  failed: "处理失败",
  cancelled: "已取消",
};

function errorText(error: unknown) {
  return error instanceof ApiClientError ? error.message : "操作未完成，请检查服务状态";
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function DocumentRow({
  document,
  index,
  onDelete,
  onRetry,
}: {
  document: DocumentRecord;
  index: number;
  onDelete: () => void;
  onRetry: () => void;
}) {
  return (
    <article className={`document-spine status-${document.status}`}>
      <div className="font-mono text-[10px] tracking-[0.18em] text-slate-400">
        DOC-{String(index + 1).padStart(3, "0")}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="truncate font-medium text-[#183541]">{document.original_filename}</h3>
          <span className="status-label">{statusLabels[document.status]}</span>
        </div>
        <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-500">
          {document.error_message || document.summary || "文件已接收，等待提取摘要和关键词。"}
        </p>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] text-slate-400">
          <span>{formatBytes(document.file_size)}</span>
          <span>{document.chunk_count} 个片段</span>
          {document.keywords.slice(0, 4).map((keyword) => (
            <span key={keyword}>#{keyword}</span>
          ))}
        </div>
      </div>
      <div className="flex items-start gap-1">
        {document.status === "failed" && (
          <button className="icon-button" onClick={onRetry} title="重新处理" type="button">
            <RefreshCw className="h-4 w-4" />
          </button>
        )}
        <button className="icon-button danger" onClick={onDelete} title="删除文献" type="button">
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </article>
  );
}

export function KnowledgeWorkspace({ onOpenReports }: { onOpenReports: () => void }) {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [filter, setFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { user, logout } = useAuthStore();

  const knowledgeBases = useQuery({
    queryKey: ["knowledge-bases"],
    queryFn: api.listKnowledgeBases,
  });
  const selected = useMemo(
    () => knowledgeBases.data?.find((item) => item.id === selectedId) ?? knowledgeBases.data?.[0],
    [knowledgeBases.data, selectedId],
  );
  const documents = useQuery({
    queryKey: ["documents", selected?.id, filter],
    queryFn: () => api.listDocuments(selected!.id, filter),
    enabled: Boolean(selected),
    refetchInterval: (query) =>
      (query.state.data as DocumentRecord[] | undefined)?.some((item) =>
        ["pending", "running"].includes(item.status),
      )
        ? 1200
        : false,
  });

  const createKnowledgeBase = useMutation({
    mutationFn: api.createKnowledgeBase,
    onSuccess: async (item) => {
      await queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
      setSelectedId(item.id);
      setCreating(false);
      setName("");
      setDescription("");
    },
    onError: (error) => setNotice(errorText(error)),
  });
  const updateKnowledgeBase = useMutation({
    mutationFn: (payload: { name: string; description?: string }) =>
      api.updateKnowledgeBase(selected!.id, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
      setIsEditing(false);
      setNotice("知识库信息已保存");
    },
    onError: (error) => setNotice(errorText(error)),
  });
  const uploadDocument = useMutation({
    mutationFn: (file: File) => api.uploadDocument(selected!.id, file),
    onSuccess: async () => {
      setNotice("文件已进入解析队列");
      await queryClient.invalidateQueries({ queryKey: ["documents", selected?.id] });
      await queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
    },
    onError: (error) => setNotice(errorText(error)),
  });
  const deleteDocument = useMutation({
    mutationFn: (documentId: string) => api.deleteDocument(selected!.id, documentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["documents", selected?.id] });
      await queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
    },
    onError: (error) => setNotice(errorText(error)),
  });
  const retryDocument = useMutation({
    mutationFn: (documentId: string) => api.retryDocument(selected!.id, documentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents", selected?.id] }),
    onError: (error) => setNotice(errorText(error)),
  });
  const search = useMutation({
    mutationFn: (query: string) => api.searchKnowledgeBase(selected!.id, query),
    onSuccess: setSearchResult,
    onError: (error) => setNotice(errorText(error)),
  });

  function submitKnowledgeBase(event: FormEvent) {
    event.preventDefault();
    createKnowledgeBase.mutate({ name, description });
  }

  function startEditing() {
    if (!selected) return;
    setEditName(selected.name);
    setEditDescription(selected.description || "");
    setIsEditing(true);
  }

  function submitUpdateKnowledgeBase(event: FormEvent) {
    event.preventDefault();
    if (!selected || !editName.trim()) return;
    updateKnowledgeBase.mutate({
      name: editName.trim(),
      description: editDescription.trim(),
    });
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    if (searchQuery.trim() && selected) search.mutate(searchQuery.trim());
  }

  function acceptFiles(files: FileList | null) {
    if (!files || !selected) return;
    Array.from(files).forEach((file) => {
      uploadDocument.mutate(file);
    });
  }

  return (
    <main className="min-h-screen bg-[#eaf0f2] p-3 text-[#183541] sm:p-5">
      <div className="mx-auto min-h-[calc(100vh-1.5rem)] max-w-[1600px] border border-[#b8c9ce] bg-[#f8fbfb] shadow-[0_30px_80px_-52px_#102f3c] sm:min-h-[calc(100vh-2.5rem)]">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[#c8d6da] px-5 py-4 lg:px-7">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center bg-[#173b49] text-white">
              <BookOpen className="h-4 w-4" />
            </span>
            <div>
              <p className="font-serif text-xl font-semibold tracking-[0.2em]">文渊</p>
              <p className="font-mono text-[10px] tracking-[0.16em] text-slate-400">RESEARCH ARCHIVE</p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <button className="quiet-action" onClick={onOpenReports} type="button">
              <FileText className="h-4 w-4" />报告装配台
            </button>
            <span className="hidden text-slate-500 sm:inline">{user?.display_name}</span>
            <button className="quiet-action" onClick={() => void logout()} type="button">
              <LogOut className="h-4 w-4" />退出
            </button>
          </div>
        </header>

        {notice && (
          <div className="flex items-center justify-between border-b border-cyan-200 bg-cyan-50 px-5 py-2 text-sm text-cyan-900">
            <span>{notice}</span>
            <button onClick={() => setNotice(null)} type="button">关闭</button>
          </div>
        )}

        <div className="grid min-h-[calc(100vh-7.5rem)] xl:grid-cols-[260px_minmax(460px,1fr)_minmax(340px,0.72fr)]">
          <aside className="border-b border-[#c8d6da] bg-[#f1f6f7] p-5 xl:border-b-0 xl:border-r">
            <div className="flex items-center justify-between">
              <p className="section-label">知识库书架</p>
              <button className="icon-button" onClick={() => setCreating(!creating)} title={creating ? "取消创建" : "新建知识库"} type="button">
                {creating ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
              </button>
            </div>
            {creating && (
              <form className="mt-4 space-y-3 border-l-2 border-cyan-600 pl-3" onSubmit={submitKnowledgeBase}>
                <input className="compact-input" value={name} onChange={(event) => setName(event.target.value)} required placeholder="知识库名称" />
                <textarea className="compact-input min-h-20 resize-none" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="对知识库的描述" />
                <button className="primary-action w-full" disabled={createKnowledgeBase.isPending} type="submit">保存知识库</button>
              </form>
            )}
            <nav className="mt-5 space-y-1" aria-label="知识库">
              {knowledgeBases.data?.map((item, index) => (
                <button
                  className={`library-spine ${selected?.id === item.id ? "active" : ""}`}
                  key={item.id}
                  onClick={() => {
                    setSelectedId(item.id);
                    setSearchResult(null);
                  }}
                  type="button"
                >
                  <span className="font-mono text-[10px] text-slate-400">KB-{String(index + 1).padStart(2, "0")}</span>
                  <span className="mt-1 block truncate font-medium">{item.name}</span>
                  <span className="mt-2 block text-xs text-slate-400">{item.document_count} 篇文献</span>
                  <ChevronRight className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 opacity-40" />
                </button>
              ))}
              {!knowledgeBases.isLoading && !knowledgeBases.data?.length && (
                <button className="empty-invitation" onClick={() => setCreating(true)} type="button">
                  <Plus className="h-4 w-4" />建立第一个知识库
                </button>
              )}
            </nav>
          </aside>

          <section className="border-b border-[#c8d6da] p-5 lg:p-7 xl:border-b-0 xl:border-r">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div className="flex-1 min-w-[280px]">
                <p className="section-label">文献归档流水</p>
                {isEditing && selected ? (
                  <form className="mt-2 space-y-3 max-w-xl border-l-2 border-cyan-600 pl-3" onSubmit={submitUpdateKnowledgeBase}>
                    <input
                      className="compact-input font-serif text-lg font-semibold"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      required
                      placeholder="知识库名称"
                    />
                    <textarea
                      className="compact-input min-h-16 resize-none text-sm"
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                      placeholder="对知识库的描述"
                    />
                    <div className="flex items-center gap-2">
                      <button className="primary-action text-xs py-1 px-3" disabled={updateKnowledgeBase.isPending} type="submit">
                        {updateKnowledgeBase.isPending ? "保存中..." : "保存"}
                      </button>
                      <button className="quiet-action text-xs py-1 px-3" onClick={() => setIsEditing(false)} type="button">
                        取消
                      </button>
                    </div>
                  </form>
                ) : (
                  <>
                    <div className="mt-2 flex items-center gap-2">
                      <h1 className="font-serif text-3xl font-semibold">{selected?.name ?? "尚未建立知识库"}</h1>
                      {selected && (
                        <button className="icon-button" onClick={startEditing} title="编辑知识库名称与描述" type="button">
                          <Pencil className="h-4 w-4 text-slate-500 hover:text-cyan-700" />
                        </button>
                      )}
                    </div>
                    <p className="mt-2 max-w-xl text-sm leading-6 text-slate-500">{selected?.description || "上传资料后，系统会保留来源位置并建立可检索片段。"}</p>
                  </>
                )}
              </div>
              {selected && (
                <button className="primary-action" onClick={() => fileInput.current?.click()} disabled={uploadDocument.isPending} type="button">
                  <Upload className="h-4 w-4" />{uploadDocument.isPending ? "正在上传" : "上传文献"}
                </button>
              )}
              <input ref={fileInput} className="hidden" type="file" multiple accept=".pdf,.md,.txt" onChange={(event) => acceptFiles(event.target.files)} />
            </div>

            {selected && (
              <div className="mt-7 flex items-center gap-3 border-y border-[#d5e0e3] py-3">
                <Search className="h-4 w-4 text-slate-400" />
                <input className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-slate-400" value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="按文件名筛选当前知识库" />
                <span className="font-mono text-[10px] text-slate-400">{documents.data?.length ?? 0} RECORDS</span>
              </div>
            )}

            <div
              className="mt-5 space-y-2"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                acceptFiles(event.dataTransfer.files);
              }}
            >
              {documents.data?.map((document, index) => (
                <DocumentRow
                  document={document}
                  index={index}
                  key={document.id}
                  onDelete={() => deleteDocument.mutate(document.id)}
                  onRetry={() => retryDocument.mutate(document.id)}
                />
              ))}
              {selected && !documents.isLoading && !documents.data?.length && (
                <button className="upload-field" onClick={() => fileInput.current?.click()} type="button">
                  <FileText className="h-6 w-6" />
                  <span className="font-medium">把第一篇文献放入档案</span>
                  <span className="text-xs text-slate-400">支持 PDF、Markdown、TXT，单文件不超过 20 MB</span>
                </button>
              )}
            </div>
          </section>

          <aside className="bg-[#f4f8f8] p-5 lg:p-7">
            <p className="section-label">检索证据台</p>
            <h2 className="mt-2 font-serif text-2xl font-semibold">询问你的资料</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">检索结果只来自当前知识库，并保留文件名、标题和页码。</p>
            <form className="mt-6" onSubmit={submitSearch}>
              <textarea className="search-box" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} disabled={!selected} placeholder="例如：哪些方法可以提高光伏功率预测精度？" />
              <button className="primary-action mt-3 w-full" disabled={!selected || search.isPending || searchQuery.trim().length < 2} type="submit">
                <FileSearch className="h-4 w-4" />{search.isPending ? "正在检索" : "检索相关片段"}
              </button>
            </form>

            <div className="mt-7 space-y-3">
              {searchResult?.results.map((result, index) => (
                <article className="evidence-slip" key={result.chunk_id}>
                  <div className="flex items-start justify-between gap-3">
                    <span className="font-mono text-[10px] tracking-[0.16em] text-cyan-700">EVIDENCE-{String(index + 1).padStart(2, "0")}</span>
                    <span className="font-mono text-xs font-semibold text-[#173b49]">{Math.round(result.similarity * 100)}%</span>
                  </div>
                  <p className="mt-3 line-clamp-5 text-sm leading-6 text-slate-600">{result.content}</p>
                  <div className="mt-4 border-t border-[#d5e0e3] pt-3 text-xs text-slate-400">
                    <p className="truncate text-slate-600">{result.document_name}</p>
                    <p className="mt-1">{result.heading || "正文"}{result.page_number ? ` · 第 ${result.page_number} 页` : ""}</p>
                  </div>
                </article>
              ))}
              {searchResult && !searchResult.results.length && <p className="empty-copy">当前资料中没有找到相关片段，请换一个更具体的问题。</p>}
              {!searchResult && <div className="empty-copy"><FileSearch className="mx-auto mb-3 h-5 w-5" />完成文献解析后，在这里验证 Top-K 检索结果。</div>}
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}
