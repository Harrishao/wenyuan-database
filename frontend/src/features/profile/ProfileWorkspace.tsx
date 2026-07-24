import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Trash2, Upload, UserCheck } from "lucide-react";

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
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.size > 2 * 1024 * 1024) {
        setNotice("头像图片大小不能超过 2MB");
        return;
      }
      const reader = new FileReader();
      reader.onload = (event) => {
        const result = event.target?.result as string;
        if (result) {
          setAvatarUrl(result);
          setNotice("头像图片已选择，保存后生效");
        }
      };
      reader.readAsDataURL(file);
    }
  };

  return (
    <main className="min-h-screen bg-[#eaf0f2] p-4 text-[#183541]">
      <div className="mx-auto max-w-5xl border border-[#b8c9ce] bg-[#f8fbfb] p-6">
        <header className="flex items-center justify-between border-b border-[#c8d6da] pb-4">
          <div>
            <h1 className="font-serif text-2xl">个人中心</h1>
            <p className="text-sm text-slate-500">资料、主题、资源用量与校园公告</p>
          </div>
          <button className="quiet-action" onClick={onBack}>
            返回工作台
          </button>
        </header>
        {notice && (
          <button className="app-toast" onClick={() => setNotice("")}>
            {notice}
          </button>
        )}
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <section className="mvp5-form">
            <h2 className="font-serif text-xl">个人资料</h2>
            <label>
              <span>账号权限</span>
              <div className="flex items-center gap-2 rounded border border-[#b9cbd0] bg-[#eef4f5] px-3 py-2 text-sm font-medium text-[#183541]">
                <UserCheck className="h-4 w-4 text-[#1687a0]" />
                <span>
                  {user?.role === "admin" ? "管理员 (admin)" : "学生账号 (student)"}
                </span>
                <span
                  className={`ml-auto rounded px-2 py-0.5 text-xs font-semibold ${
                    user?.role === "admin"
                      ? "bg-amber-100 text-amber-800"
                      : "bg-emerald-100 text-emerald-800"
                  }`}
                >
                  {user?.role === "admin" ? "ADMIN" : "STUDENT"}
                </span>
              </div>
            </label>
            <label>
              <span>昵称</span>
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </label>
            <label>
              <span>用户头像</span>
              <div className="flex items-center gap-4 pt-1">
                <div className="relative flex h-14 w-14 items-center justify-center overflow-hidden rounded-full border-2 border-[#1687a0] bg-slate-100 shadow-sm">
                  {avatarUrl ? (
                    <img
                      src={avatarUrl}
                      alt="Avatar"
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <span className="font-serif text-lg font-bold text-[#1687a0]">
                      {displayName.slice(0, 2).toUpperCase() || "U"}
                    </span>
                  )}
                </div>
                <div className="flex flex-col gap-2">
                  <input
                    type="file"
                    ref={fileInputRef}
                    accept="image/*"
                    className="hidden"
                    onChange={handleFileChange}
                  />
                  <button
                    type="button"
                    className="inline-flex items-center gap-1.5 rounded border border-[#173b49] bg-[#173b49] px-3 py-1.5 text-xs text-white transition-colors hover:bg-[#1687a0]"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload className="h-3.5 w-3.5" />
                    点击上传头像
                  </button>
                  {avatarUrl && (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 text-xs text-rose-600 hover:underline"
                      onClick={() => setAvatarUrl("")}
                    >
                      <Trash2 className="h-3 w-3" />
                      移除头像
                    </button>
                  )}
                </div>
              </div>
            </label>
            <label>
              <span>个人简介</span>
              <textarea
                value={bio}
                onChange={(event) => setBio(event.target.value)}
              />
            </label>
            <button
              className="primary-action"
              disabled={save.isPending}
              onClick={() => save.mutate()}
            >
              保存资料
            </button>
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
                        setNotice(
                          error instanceof ApiClientError ? error.message : "发送失败",
                        );
                      }
                    }}
                  >
                    发送验证邮件
                  </button>
                ) : (
                  <>
                    <input
                      value={verificationCode}
                      onChange={(event) => setVerificationCode(event.target.value)}
                      placeholder="6 位验证码"
                    />
                    <button
                      onClick={async () => {
                        try {
                          await api.confirmEmailCode({
                            email: user!.email,
                            purpose: "verify_email",
                            code: verificationCode,
                          });
                          replaceUser(await api.me());
                          setNotice("邮箱验证完成");
                        } catch (error) {
                          setNotice(
                            error instanceof ApiClientError ? error.message : "验证失败",
                          );
                        }
                      }}
                    >
                      确认验证码
                    </button>
                  </>
                )}
              </div>
            )}
          </section>
          <section className="mvp5-form">
            <h2 className="font-serif text-xl">外观与用量</h2>
            <label>
              <span>主题</span>
              <select
                value={theme}
                onChange={(event) => setTheme(event.target.value)}
              >
                <option value="light">浅色 (学府青灰 · 典雅严谨)</option>
                <option value="warm">温馨 (暖阁纸香 · 柔和舒适)</option>
                <option value="dark">深色 (夜读墨蓝 · 沉浸护眼)</option>
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <div className="border p-3">
                <strong>{usage.data?.knowledge_base_count ?? 0}</strong>
                <p>知识库</p>
              </div>
              <div className="border p-3">
                <strong>{usage.data?.document_count ?? 0}</strong>
                <p>文献</p>
              </div>
              <div className="border p-3">
                <strong>{usage.data?.report_count ?? 0}</strong>
                <p>报告</p>
              </div>
              <div className="border p-3">
                <strong>{formatBytes(usage.data?.storage_bytes ?? 0)}</strong>
                <p>磁盘占用</p>
              </div>
              <div className="border p-3">
                <strong>{usage.data?.model_call_count ?? 0}</strong>
                <p>模型任务</p>
              </div>
            </div>
          </section>
        </div>
        <section className="mt-6 border border-[#c8d6da] bg-white p-5">
          <h2 className="font-serif text-xl">校园公告</h2>
          <div className="mt-3 grid gap-3">
            {announcements.data?.map((item) => (
              <article className="border-l-2 border-cyan-700 pl-4" key={item.id}>
                <strong>
                  {item.pinned ? "置顶 · " : ""}
                  {item.title}
                </strong>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">
                  {item.content}
                </p>
              </article>
            ))}
            {!announcements.data?.length && (
              <p className="text-sm text-slate-500">当前没有有效公告。</p>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
