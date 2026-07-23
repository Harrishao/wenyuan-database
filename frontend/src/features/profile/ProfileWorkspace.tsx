import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { useAuthStore } from "@/features/auth/auth-store";
import { ApiClientError, api } from "@/lib/api-client";

function formatBytes(bytes: number) {
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export function ProfileWorkspace({ onBack }: { onBack: () => void }) {
  const { user, replaceUser } = useAuthStore();
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [avatarUrl, setAvatarUrl] = useState(user?.avatar_url ?? "");
  const [bio, setBio] = useState(user?.bio ?? "");
  const [notice, setNotice] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [verificationSent, setVerificationSent] = useState(false);
  const [theme, setTheme] = useState(
    () => localStorage.getItem("wenyuan-theme") ?? "light",
  );
  const usage = useQuery({ queryKey: ["my-usage"], queryFn: api.getUsage });
  const announcements = useQuery({
    queryKey: ["announcements"],
    queryFn: api.listAnnouncements,
  });
  const save = useMutation({
    mutationFn: () =>
      api.updateProfile({
        display_name: displayName,
        avatar_url: avatarUrl,
        bio,
      }),
    onSuccess: (updated) => {
      replaceUser(updated);
      setNotice("个人资料已更新");
    },
    onError: (error) =>
      setNotice(error instanceof ApiClientError ? error.message : "保存失败"),
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("wenyuan-theme", theme);
  }, [theme]);

  return (
    <main className="min-h-screen bg-[#eaf0f2] p-4 text-[#183541]">
      <div className="mx-auto max-w-5xl border border-[#b8c9ce] bg-[#f8fbfb] p-6">
        <header className="flex items-center justify-between border-b border-[#c8d6da] pb-4">
          <div><h1 className="font-serif text-2xl">个人中心</h1><p className="text-sm text-slate-500">资料、主题、资源用量与校园公告</p></div>
          <button className="quiet-action" onClick={onBack}>返回工作台</button>
        </header>
        {notice && <button className="app-toast" onClick={() => setNotice("")}>{notice}</button>}
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <section className="mvp5-form">
            <h2 className="font-serif text-xl">个人资料</h2>
            <label>昵称<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label>
            <label>头像地址<input value={avatarUrl} onChange={(event) => setAvatarUrl(event.target.value)} placeholder="https://..." /></label>
            <label>个人简介<textarea value={bio} onChange={(event) => setBio(event.target.value)} /></label>
            <button className="primary-action" disabled={save.isPending} onClick={() => save.mutate()}>保存资料</button>
            {!user?.email_verified && (
              <div className="section-editor">
                <strong>邮箱尚未验证</strong>
                {!verificationSent ? (
                  <button
                    onClick={async () => {
                      try {
                        await api.requestEmailCode(user!.email, "verify_email");
                        setVerificationSent(true);
                        setNotice("验证码已发送");
                      } catch (error) {
                        setNotice(error instanceof ApiClientError ? error.message : "发送失败");
                      }
                    }}
                  >
                    发送验证邮件
                  </button>
                ) : (
                  <>
                    <input value={verificationCode} onChange={(event) => setVerificationCode(event.target.value)} placeholder="6 位验证码" />
                    <button onClick={async () => {
                      try {
                        await api.confirmEmailCode({ email: user!.email, purpose: "verify_email", code: verificationCode });
                        replaceUser(await api.me());
                        setNotice("邮箱验证完成");
                      } catch (error) {
                        setNotice(error instanceof ApiClientError ? error.message : "验证失败");
                      }
                    }}>确认验证码</button>
                  </>
                )}
              </div>
            )}
          </section>
          <section className="mvp5-form">
            <h2 className="font-serif text-xl">外观与用量</h2>
            <label>主题
              <select value={theme} onChange={(event) => setTheme(event.target.value)}>
                <option value="light">浅色</option><option value="dark">深色</option>
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <div className="border p-3"><strong>{usage.data?.knowledge_base_count ?? 0}</strong><p>知识库</p></div>
              <div className="border p-3"><strong>{usage.data?.document_count ?? 0}</strong><p>文献</p></div>
              <div className="border p-3"><strong>{usage.data?.report_count ?? 0}</strong><p>报告</p></div>
              <div className="border p-3"><strong>{formatBytes(usage.data?.storage_bytes ?? 0)}</strong><p>磁盘占用</p></div>
              <div className="border p-3"><strong>{usage.data?.model_call_count ?? 0}</strong><p>模型任务</p></div>
            </div>
          </section>
        </div>
        <section className="mt-6 border border-[#c8d6da] bg-white p-5">
          <h2 className="font-serif text-xl">校园公告</h2>
          <div className="mt-3 grid gap-3">
            {announcements.data?.map((item) => (
              <article className="border-l-2 border-cyan-700 pl-4" key={item.id}>
                <strong>{item.pinned ? "置顶 · " : ""}{item.title}</strong>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{item.content}</p>
              </article>
            ))}
            {!announcements.data?.length && <p className="text-sm text-slate-500">当前没有有效公告。</p>}
          </div>
        </section>
        <section className="mt-6 border border-[#c8d6da] bg-white p-5">
          <h2 className="font-serif text-xl">常见错误码</h2>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div><dt>AUTH_REFRESH_INVALID</dt><dd>会话已过期，请重新登录。</dd></div>
            <div><dt>DOCUMENT_DUPLICATE</dt><dd>同一知识库已经存在相同文件。</dd></div>
            <div><dt>REFERENCE_METADATA_INCOMPLETE</dt><dd>补齐文献作者、年份和来源后再导出。</dd></div>
            <div><dt>TEMPLATE_IN_USE</dt><dd>模板已被历史报告引用，不能物理删除。</dd></div>
          </dl>
        </section>
      </div>
    </main>
  );
}
