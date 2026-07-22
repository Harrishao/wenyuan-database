import { useEffect } from "react";

import { AuthPage } from "@/features/auth/AuthPage";
import { useAuthStore } from "@/features/auth/auth-store";
import { KnowledgeWorkspace } from "@/features/knowledge/KnowledgeWorkspace";

export function AuthGate() {
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

  return user ? <KnowledgeWorkspace /> : <AuthPage />;
}
