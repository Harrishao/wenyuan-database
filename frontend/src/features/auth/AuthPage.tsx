import { FormEvent, useEffect, useState } from "react";
import { BookOpen, LockKeyhole } from "lucide-react";

import { useAuthStore } from "@/features/auth/auth-store";
import { ApiClientError, api } from "@/lib/api-client";

const displayNameExamples = [
  "尊贵的研究员",
  "峡谷召唤师",
  "沃尔玛塑料袋",
  "愤怒的迪克",
  "夜读学术星",
  "猫娘学院高材生",
  "图灵教派信徒",
  "冯诺依曼教派信徒",
  "量子力学幽灵",
  "武装直升机",
  "大魔导师",
];

export function AuthPage() {
  const [exampleIndex, setExampleIndex] = useState(0);
  const [mode, setMode] = useState<"login" | "register" | "recover">("login");
  const [displayName, setDisplayName] = useState("");

  useEffect(() => {
    if (mode !== "register") return;
    const timer = window.setInterval(() => {
      setExampleIndex((prev) => (prev + 1) % displayNameExamples.length);
    }, 2200);
    return () => window.clearInterval(timer);
  }, [mode]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { login, register } = useAuthStore();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode === "register") await register(displayName, email, password);
      else if (mode === "recover") {
        if (!codeSent) {
          await api.requestEmailCode(email, "reset_password");
          setCodeSent(true);
          setError("验证码已发送，请查收邮件并填写新密码");
        } else {
          await api.confirmEmailCode({
            email,
            purpose: "reset_password",
            code,
            new_password: password,
          });
          setMode("login");
          setCodeSent(false);
          setCode("");
          setError("密码已重置，请使用新密码登录");
        }
      } else await login(email, password);
    } catch (caught) {
      setError(caught instanceof ApiClientError ? caught.message : "无法连接服务，请检查一键启动窗口");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#edf3f5] px-5 py-8 text-[#132a36] sm:px-10 lg:px-16">
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-7xl overflow-hidden border border-[#b9cbd1] bg-[#f8fbfb] shadow-[0_32px_90px_-52px_#133744] lg:grid-cols-[1.18fr_0.82fr]">
        <section className="relative flex min-h-[38rem] flex-col justify-between overflow-hidden bg-[#153746] p-8 text-white sm:p-12 lg:p-16">
          <div className="archive-grid absolute inset-0 opacity-25" aria-hidden="true" />
          <header className="relative flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center border border-white/30">
              <BookOpen className="h-5 w-5" />
            </span>
            <div>
              <p className="font-serif text-2xl font-semibold tracking-[0.24em]">文渊</p>
              <p className="mt-1 text-xs tracking-[0.18em] text-cyan-100/70">PRIVATE RESEARCH ARCHIVE</p>
            </div>
          </header>

          <div className="relative max-w-2xl">
            <p className="mb-5 font-mono text-xs tracking-[0.22em] text-[#63d5de]">ARCHIVE / 001</p>
            <h1 className="font-serif text-5xl font-semibold leading-[1.16] sm:text-6xl">
              让每一条论述，
              <br />
              都能回到原文。
            </h1>
            <p className="mt-7 max-w-xl text-base leading-8 text-slate-200">
              归档文献、追踪处理状态，并从你的私有资料中检索可验证的研究证据。
            </p>
          </div>

          <div className="relative grid grid-cols-3 border-t border-white/20 pt-5 text-xs text-slate-300">
            <span>PDF</span>
            <span>MARKDOWN</span>
            <span>PLAIN TEXT</span>
          </div>
        </section>

        <section className="flex items-center px-7 py-12 sm:px-12 lg:px-16">
          <div className="w-full max-w-md">
            <p className="font-mono text-xs tracking-[0.18em] text-cyan-700">
              {mode === "login" ? "RETURN TO ARCHIVE" : mode === "recover" ? "RECOVER ACCOUNT" : "CREATE RESEARCH ID"}
            </p>
            <h2 className="mt-4 font-serif text-4xl font-semibold text-[#132a36]">
              {mode === "login" ? "继续整理你的资料" : mode === "recover" ? "找回账号密码" : "建立你的研究档案"}
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-500">
              {mode === "login" ? "使用邮箱和密码进入工作台。" : mode === "recover" ? "验证码十分钟内有效，使用后立即失效。" : "创建账号后即可建立第一个私有知识库。"}
            </p>

            <form className="mt-9 space-y-5" onSubmit={submit}>
              {mode === "register" && (
                <label className="block">
                  <span className="field-label">称呼</span>
                  <input
                    className="field-input"
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    minLength={2}
                    maxLength={80}
                    required
                    placeholder={`例如：${displayNameExamples[exampleIndex]}`}
                  />
                </label>
              )}
              <label className="block">
                <span className="field-label">邮箱</span>
                <input
                  className="field-input"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  type="email"
                  autoComplete="email"
                  required
                  placeholder="name@example.com"
                />
              </label>
              {mode !== "recover" || codeSent ? <label className="block">
                <span className="field-label">密码</span>
                <input
                  className="field-input"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  minLength={8}
                  required={mode !== "recover" || codeSent}
                  placeholder="至少 8 位字符"
                />
              </label> : null}
              {mode === "recover" && codeSent && (
                <label className="block">
                  <span className="field-label">邮箱验证码</span>
                  <input className="field-input" value={code} onChange={(event) => setCode(event.target.value)} pattern="\d{6}" required placeholder="6 位验证码" />
                </label>
              )}

              {error && <p className="border-l-2 border-red-500 pl-3 text-sm text-red-700">{error}</p>}

              <button className="primary-action w-full" disabled={submitting} type="submit">
                <LockKeyhole className="h-4 w-4" />
                {submitting ? "正在验证" : mode === "login" ? "进入研究档案" : mode === "recover" ? codeSent ? "确认重置密码" : "发送验证码" : "创建并进入"}
              </button>
            </form>

            <button
              className="mt-6 text-sm text-slate-500 underline decoration-slate-300 underline-offset-4 hover:text-cyan-800"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError(null);
              }}
              type="button"
            >
              {mode === "login" ? "还没有账号？创建研究档案" : "已有账号？返回登录"}
            </button>
            {mode === "login" && (
              <button
                className="ml-4 mt-6 text-sm text-slate-500 underline decoration-slate-300 underline-offset-4"
                onClick={() => { setMode("recover"); setError(null); setCodeSent(false); }}
                type="button"
              >
                忘记密码
              </button>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
