import { useEffect, useState } from "react";

import { AuthPage } from "@/features/auth/AuthPage";
import { useAuthStore } from "@/features/auth/auth-store";
import { KnowledgeWorkspace } from "@/features/knowledge/KnowledgeWorkspace";
import { ReportWorkspace } from "@/features/reports/ReportWorkspace";

export function AuthGate() {
  const [workspace, setWorkspace] = useState<"knowledge" | "reports">("knowledge");
  const { user, initializing, bootstrap } = useAuthStore();

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  if (initializing) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f3f7f8] text-sm text-slate-500">
        正在恢复研究档案…
      </main>
    );
  }

  if (!user) return <AuthPage />;
  return workspace === "knowledge" ? (
    <KnowledgeWorkspace onOpenReports={() => setWorkspace("reports")} />
  ) : (
    <ReportWorkspace onOpenKnowledge={() => setWorkspace("knowledge")} />
  );
}
