import { useQuery } from "@tanstack/react-query";
import { BookOpenText, Database, ServerCog } from "lucide-react";

import { api } from "@/lib/api-client";

const contracts = [
  { icon: BookOpenText, name: "知识库", detail: "文献、片段与向量契约已建立" },
  { icon: Database, name: "数据层", detail: "PostgreSQL 与 pgvector 统一存储" },
  { icon: ServerCog, name: "适配层", detail: "LLM、Embedding 与文件存储可替换" },
];

export function FoundationPage() {
  const health = useQuery({
    queryKey: ["health", "live"],
    queryFn: api.getLiveness,
    refetchInterval: 15_000,
  });

  return (
    <main className="min-h-screen px-6 py-12 sm:px-10 lg:px-16">
      <div className="mx-auto max-w-6xl">
        <header className="mb-16 flex items-center justify-between border-b border-slate-200 pb-5">
          <div>
            <p className="font-serif text-2xl font-semibold tracking-[0.18em] text-slate-950">文渊</p>
            <p className="mt-1 text-sm text-slate-500">大学生私有文献知识库</p>
          </div>
          <span className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-600">
            MVP 0
          </span>
        </header>

        <section className="grid gap-10 lg:grid-cols-[1.25fr_0.75fr] lg:items-end">
          <div>
            <p className="mb-4 text-sm font-semibold tracking-[0.2em] text-cyan-700">FOUNDATION READY</p>
            <h1 className="font-serif text-5xl font-semibold leading-tight text-slate-950 sm:text-6xl">
              从可信的领域契约，
              <br />
              开始构建知识链路。
            </h1>
            <p className="mt-7 max-w-2xl text-lg leading-8 text-slate-600">
              前后端边界、数据模型与基础设施端口已经就位。下一阶段将接入真实文献，完成解析、切片和检索闭环。
            </p>
          </div>

          <aside className="rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_18px_60px_-35px_rgba(15,23,42,0.35)]">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-slate-500">后端服务</span>
              <span
                className={`h-2.5 w-2.5 rounded-full ${health.isSuccess ? "bg-emerald-500" : "bg-amber-500"}`}
              />
            </div>
            <p className="mt-3 text-xl font-semibold text-slate-900">
              {health.isPending && "正在检查"}
              {health.isSuccess && `${health.data.name} · ${health.data.status}`}
              {health.isError && "尚未连接"}
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              {health.isError
                ? "请启动 FastAPI 服务，页面会自动重新检查。"
                : "健康检查通过后，前端即可使用同一套 API 契约继续扩展。"}
            </p>
          </aside>
        </section>

        <section className="mt-16 grid gap-4 md:grid-cols-3">
          {contracts.map(({ icon: Icon, name, detail }) => (
            <article key={name} className="rounded-xl border border-slate-200 bg-white/80 p-5">
              <Icon aria-hidden="true" className="h-5 w-5 text-cyan-700" />
              <h2 className="mt-6 font-semibold text-slate-900">{name}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-500">{detail}</p>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
