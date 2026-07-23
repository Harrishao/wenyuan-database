import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  AdminTemplateSection,
  Announcement,
  ModerationItem,
} from "@/contracts/api";
import { ApiClientError, api } from "@/lib/api-client";

function message(error: unknown) {
  return error instanceof ApiClientError || error instanceof Error
    ? error.message
    : "操作失败";
}

const emptySection = (position: number): AdminTemplateSection => ({
  key: `section_${position}`,
  title: `章节 ${position}`,
  position,
  instructions: "",
  required_inputs: [],
});

export function TemplateManagement() {
  const client = useQueryClient();
  const templates = useQuery({
    queryKey: ["admin-templates"],
    queryFn: api.listAdminTemplates,
  });
  const [selectedId, setSelectedId] = useState("");
  const selected = templates.data?.find((item) => item.id === selectedId);
  const [meta, setMeta] = useState({ key: "", name: "", description: "" });
  const [prompt, setPrompt] = useState("仅依据提供的私有知识库证据生成章节，并保留引用编号。");
  const [topK, setTopK] = useState(4);
  const [wordCount, setWordCount] = useState(1200);
  const [sections, setSections] = useState<AdminTemplateSection[]>([emptySection(1)]);
  const [notice, setNotice] = useState("");

  const refresh = () =>
    client.invalidateQueries({ queryKey: ["admin-templates"] });
  const saveMeta = useMutation({
    mutationFn: () =>
      selected
        ? api.updateAdminTemplate(selected.id, meta)
        : api.createAdminTemplate(meta),
    onSuccess: async (item) => {
      setSelectedId(item.id);
      setNotice("模板基本信息已保存");
      await refresh();
    },
    onError: (error) => setNotice(message(error)),
  });
  const publish = useMutation({
    mutationFn: () =>
      api.publishAdminTemplate(selectedId, {
        system_prompt: prompt,
        settings: { top_k: topK, target_words: wordCount },
        sections,
      }),
    onSuccess: async () => {
      setNotice("新版本已发布，旧报告仍绑定原模板版本");
      await refresh();
    },
    onError: (error) => setNotice(message(error)),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteAdminTemplate(selectedId),
    onSuccess: async () => {
      setSelectedId("");
      setMeta({ key: "", name: "", description: "" });
      setNotice("未被报告引用的模板已删除");
      await refresh();
    },
    onError: (error) => setNotice(message(error)),
  });

  function selectTemplate(id: string) {
    setSelectedId(id);
    const item = templates.data?.find((candidate) => candidate.id === id);
    if (!item) return;
    setMeta({
      key: item.key,
      name: item.name,
      description: item.description ?? "",
    });
    const latest = item.versions[0];
    if (latest) {
      setPrompt(latest.system_prompt);
      setTopK(Number(latest.settings.top_k ?? 4));
      setWordCount(Number(latest.settings.target_words ?? 1200));
      setSections(latest.sections);
    }
  }

  function patchSection(index: number, patch: Partial<AdminTemplateSection>) {
    setSections((items) =>
      items.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item,
      ),
    );
  }

  function moveSection(index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= sections.length) return;
    const next = [...sections];
    [next[index], next[target]] = [next[target], next[index]];
    setSections(next.map((item, position) => ({ ...item, position: position + 1 })));
  }

  return (
    <section className="mvp5-panel">
      <header>
        <h2>报告模板管理</h2>
        <p>维护模板基本信息、章节顺序、生成参数，并以不可变版本发布。</p>
      </header>
      {notice && <button className="control-notice" onClick={() => setNotice("")}>{notice}</button>}
      <div className="mvp5-grid">
        <aside>
          <button className="primary-action" onClick={() => {
            setSelectedId("");
            setMeta({ key: "", name: "", description: "" });
            setSections([emptySection(1)]);
          }}>新建模板</button>
          {templates.data?.map((item) => (
            <button
              className={`mvp5-list-item ${item.id === selectedId ? "active" : ""}`}
              key={item.id}
              onClick={() => selectTemplate(item.id)}
            >
              <strong>{item.name}</strong>
              <span>{item.status} · {item.versions[0] ? `v${item.versions[0].version}` : "未发布"}</span>
            </button>
          ))}
        </aside>
        <div className="mvp5-form">
          <label>模板标识<input value={meta.key} onChange={(event) => setMeta({ ...meta, key: event.target.value })} /></label>
          <label>名称<input value={meta.name} onChange={(event) => setMeta({ ...meta, name: event.target.value })} /></label>
          <label>说明<textarea value={meta.description} onChange={(event) => setMeta({ ...meta, description: event.target.value })} /></label>
          <div className="mvp5-actions">
            <button className="primary-action" disabled={!meta.key || !meta.name || saveMeta.isPending} onClick={() => saveMeta.mutate()}>保存基本信息</button>
            {selected && <button className="danger-action" onClick={() => remove.mutate()}>安全删除</button>}
          </div>
          {selected && (
            <>
              <hr />
              <label>系统提示词<textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} /></label>
              <div className="mvp5-inline">
                <label>检索数量<input type="number" min={1} max={20} value={topK} onChange={(event) => setTopK(Number(event.target.value))} /></label>
                <label>目标字数<input type="number" min={100} value={wordCount} onChange={(event) => setWordCount(Number(event.target.value))} /></label>
              </div>
              <h3>章节配置</h3>
              {sections.map((section, index) => (
                <div className="section-editor" key={`${section.key}-${index}`}>
                  <div className="mvp5-inline">
                    <input value={section.key} onChange={(event) => patchSection(index, { key: event.target.value })} placeholder="章节标识" />
                    <input value={section.title} onChange={(event) => patchSection(index, { title: event.target.value })} placeholder="章节标题" />
                  </div>
                  <textarea value={section.instructions} onChange={(event) => patchSection(index, { instructions: event.target.value })} placeholder="章节说明" />
                  <input
                    value={section.required_inputs.join(",")}
                    onChange={(event) => patchSection(index, { required_inputs: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })}
                    placeholder="必填输入，逗号分隔"
                  />
                  <div className="mvp5-actions">
                    <button onClick={() => moveSection(index, -1)}>上移</button>
                    <button onClick={() => moveSection(index, 1)}>下移</button>
                    <button onClick={() => setSections((items) => items.filter((_, itemIndex) => itemIndex !== index).map((item, position) => ({ ...item, position: position + 1 })))}>删除章节</button>
                  </div>
                </div>
              ))}
              <div className="mvp5-actions">
                <button onClick={() => setSections((items) => [...items, emptySection(items.length + 1)])}>新增章节</button>
                <button className="primary-action" disabled={!sections.length || publish.isPending} onClick={() => publish.mutate()}>发布新版本</button>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

export function ModerationManagement() {
  const client = useQueryClient();
  const [status, setStatus] = useState("");
  const [note, setNote] = useState("");
  const [notice, setNotice] = useState("");
  const items = useQuery({
    queryKey: ["admin-moderation", status],
    queryFn: () => api.listModeration(status),
  });
  const action = useMutation({
    mutationFn: ({ item, next, disable = false, permanent = false }: { item: ModerationItem; next: ModerationItem["status"]; disable?: boolean; permanent?: boolean }) =>
      api.moderateContent(item, { status: next, note, disable_user: disable, permanent_delete: permanent }),
    onSuccess: async () => {
      setNotice("审核处置已保存并写入审计日志");
      setNote("");
      await client.invalidateQueries({ queryKey: ["admin-moderation"] });
    },
    onError: (error) => setNotice(message(error)),
  });
  return (
    <section className="mvp5-panel">
      <header><h2>内容审核流水线</h2><p>敏感词命中从待审核到通过、限制、下架或彻底删除形成闭环。</p></header>
      {notice && <button className="app-toast" onClick={() => setNotice("")}>{notice}</button>}
      <div className="mvp5-toolbar">
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">全部状态</option><option value="pending">待审核</option>
          <option value="approved">已通过</option><option value="restricted">已限制</option>
          <option value="removed">已下架</option>
        </select>
        <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="审核意见" />
      </div>
      <div className="mvp5-cards">
        {items.data?.map((item) => (
          <article key={`${item.content_type}-${item.content_id}`}>
            <div><strong>{item.title}</strong><span>{item.owner_display_name} · {item.status}</span></div>
            <p>{item.summary || "无摘要"}</p>
            <small>命中 {item.hits.length} 项 · {new Date(item.created_at).toLocaleString()}</small>
            <div className="mvp5-actions">
              <button onClick={() => action.mutate({ item, next: "approved" })}>通过</button>
              <button onClick={() => action.mutate({ item, next: "restricted" })}>限制使用</button>
              <button onClick={() => action.mutate({ item, next: "removed" })}>下架</button>
              <button onClick={() => action.mutate({ item, next: "removed", permanent: true })}>彻底删除</button>
              <button onClick={() => action.mutate({ item, next: "restricted", disable: true })}>限制并封禁用户</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

const emptyAnnouncement: Omit<
  Announcement,
  "id" | "created_at" | "updated_at"
> = {
  title: "",
  content: "",
  pinned: false,
  published_at: null,
  expires_at: null,
  is_published: false,
};

export function AnnouncementManagement() {
  const client = useQueryClient();
  const announcements = useQuery({
    queryKey: ["admin-announcements"],
    queryFn: api.listAdminAnnouncements,
  });
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState(emptyAnnouncement);
  const save = useMutation({
    mutationFn: () => api.saveAnnouncement(editing, form),
    onSuccess: async () => {
      setEditing(null);
      setForm(emptyAnnouncement);
      await client.invalidateQueries({ queryKey: ["admin-announcements"] });
    },
  });
  const remove = useMutation({
    mutationFn: api.deleteAnnouncement,
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin-announcements"] }),
  });
  function edit(item: Announcement) {
    setEditing(item.id);
    setForm({
      title: item.title,
      content: item.content,
      pinned: item.pinned,
      published_at: item.published_at,
      expires_at: item.expires_at,
      is_published: item.is_published,
    });
  }
  return (
    <section className="mvp5-panel">
      <header><h2>校园公告</h2><p>创建、编辑、发布、置顶和按时间自动下线。</p></header>
      <div className="mvp5-grid">
        <aside>
          <button className="primary-action" onClick={() => { setEditing(null); setForm(emptyAnnouncement); }}>新建公告</button>
          {announcements.data?.map((item) => (
            <button className="mvp5-list-item" key={item.id} onClick={() => edit(item)}>
              <strong>{item.title}</strong><span>{item.is_published ? "已发布" : "草稿"}{item.pinned ? " · 置顶" : ""}</span>
            </button>
          ))}
        </aside>
        <div className="mvp5-form">
          <label>标题<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
          <label>正文<textarea className="tall" value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} /></label>
          <div className="mvp5-inline">
            <label><input type="checkbox" checked={form.pinned} onChange={(event) => setForm({ ...form, pinned: event.target.checked })} />置顶</label>
            <label><input type="checkbox" checked={form.is_published} onChange={(event) => setForm({ ...form, is_published: event.target.checked })} />发布</label>
          </div>
          <div className="mvp5-actions">
            <button className="primary-action" disabled={!form.title || !form.content} onClick={() => save.mutate()}>保存公告</button>
            {editing && <button className="danger-action" onClick={() => remove.mutate(editing)}>删除公告</button>}
          </div>
        </div>
      </div>
    </section>
  );
}
