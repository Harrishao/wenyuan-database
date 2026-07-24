import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  Braces,
  ChevronLeft,
  ChevronRight,
  CircleGauge,
  Database,
  FileClock,
  KeyRound,
  LayoutTemplate,
  Megaphone,
  Plus,
  RefreshCw,
  Save,
  Server,
  ShieldCheck,
  Gavel,
  Trash2,
  Users,
  X,
} from "lucide-react";

import type {
  ApplicationLog,
  EmbeddingPreset,
  LlmPreset,
  PromptMessage,
  PromptPreset,
  ServerStatus,
} from "@/contracts/api";
import { ApiClientError, api } from "@/lib/api-client";
import {
  AnnouncementManagement,
  ModerationManagement,
  TemplateManagement,
} from "@/features/admin/Mvp5AdminPanel";

type AdminTab =
  | "dashboard"
  | "llm"
  | "prompt"
  | "embedding"
  | "safety"
  | "templates"
  | "moderation"
  | "announcements"
  | "users"
  | "audit";

const emptyLlmForm = {
  name: "",
  base_url: "",
  api_key: "",
  model: "",
  parameters: '{\n  "temperature": 0.7,\n  "max_tokens": 8192\n}',
  context_window_tokens: 128000,
  max_output_tokens: 4096,
  history_turn_limit: 12,
  input_credits_per_million_tokens: 0,
  output_credits_per_million_tokens: 0,
  usage_mode: "auto" as "auto" | "reported" | "estimated",
  bound_prompt_preset_id: "",
  bound_embedding_preset_id: "",
};

const emptyEmbeddingForm = {
  name: "",
  provider: "local_hashing" as "local_hashing" | "openai_compatible",
  base_url: "",
  api_key: "",
  model: "local-char-ngram-hashing-v1",
  dimensions: 512,
  parameters: "{}",
};

const emptyPromptMessage = (position: number): PromptMessage => ({
  name: `消息 ${position + 1}`,
  role: "system",
  content: "",
  enabled: true,
  position,
});

const emptyPromptForm = {
  name: "",
  description: "",
  capability: "report_generation" as PromptPreset["capability"],
  variant_key: "default",
  messages: [emptyPromptMessage(0)],
};

function errorText(error: unknown) {
  if (error instanceof ApiClientError) return error.message;
  if (error instanceof Error) return error.message;
  return "操作未完成，请检查输入与服务状态";
}

function parseParameters(value: string): Record<string, unknown> {
  const parsed = value.trim() ? (JSON.parse(value) as unknown) : {};
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("附加参数必须是 JSON 对象");
  }
  return parsed as Record<string, unknown>;
}

function formatBytes(bytes: number) {
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function TelemetryChart({ samples }: { samples: ServerStatus[] }) {
  const width = 700;
  const height = 190;
  const points = (key: "cpu_percent" | "memory_percent") =>
    samples
      .map((sample, index) => {
        const x =
          samples.length === 1 ? 0 : (index / (samples.length - 1)) * width;
        const y = height - (sample[key] / 100) * height;
        return `${x},${y}`;
      })
      .join(" ");
  return (
    <svg
      className="telemetry-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
    >
      {[0, 25, 50, 75, 100].map((value) => (
        <line
          key={value}
          x1="0"
          x2={width}
          y1={height - value * 1.9}
          y2={height - value * 1.9}
        />
      ))}
      <polyline className="memory-line" points={points("memory_percent")} />
      <polyline className="cpu-line" points={points("cpu_percent")} />
    </svg>
  );
}

export function AdminWorkspace({ onBack }: { onBack: () => void }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<AdminTab>("dashboard");
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedLlmId, setSelectedLlmId] = useState("");
  const [selectedPromptId, setSelectedPromptId] = useState("");
  const [selectedEmbeddingId, setSelectedEmbeddingId] = useState("");
  const [llmForm, setLlmForm] = useState(emptyLlmForm);
  const [embeddingForm, setEmbeddingForm] = useState(emptyEmbeddingForm);
  const [promptForm, setPromptForm] = useState(emptyPromptForm);
  const [capabilityForm, setCapabilityForm] = useState({ key: "", name: "" });
  const [activeMessageIndex, setActiveMessageIndex] = useState(0);
  const [models, setModels] = useState<string[]>([]);
  const [groupForm, setGroupForm] = useState({
    originalName: "",
    name: "",
    terms: "",
    enabled: true,
  });
  const [auditFilters, setAuditFilters] = useState({
    action: "",
    actor_user_id: "",
    start_at: "",
    end_at: "",
  });
  const [logLevel, setLogLevel] = useState("");
  const [telemetry, setTelemetry] = useState<ServerStatus[]>([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1024) {
        setSidebarCollapsed(true);
      }
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const runtime = useQuery({
    queryKey: ["admin-runtime"],
    queryFn: api.getRuntimeConfig,
  });
  const llms = useQuery({
    queryKey: ["admin-llms"],
    queryFn: api.listLlmPresets,
  });
  const prompts = useQuery({
    queryKey: ["admin-prompts"],
    queryFn: api.listPromptPresets,
  });
  const promptCapabilities = useQuery({
    queryKey: ["admin-prompt-capabilities"],
    queryFn: api.listPromptCapabilities,
  });
  const embeddings = useQuery({
    queryKey: ["admin-embeddings"],
    queryFn: api.listEmbeddingPresets,
  });
  const groups = useQuery({
    queryKey: ["admin-sensitive-groups"],
    queryFn: api.listSensitiveGroups,
  });
  const users = useQuery({
    queryKey: ["admin-users"],
    queryFn: api.listAdminUsers,
  });
  const audits = useQuery({
    queryKey: ["admin-audits", auditFilters],
    queryFn: () =>
      api.listAuditLogs({
        ...auditFilters,
        start_at: auditFilters.start_at
          ? new Date(auditFilters.start_at).toISOString()
          : undefined,
        end_at: auditFilters.end_at
          ? new Date(auditFilters.end_at).toISOString()
          : undefined,
      }),
  });
  const logs = useQuery({
    queryKey: ["admin-application-logs", logLevel],
    queryFn: () => api.listApplicationLogs(logLevel),
    enabled: tab === "dashboard",
    refetchInterval: 3000,
  });

  useEffect(() => {
    if (tab !== "dashboard") return;
    let alive = true;
    const sample = async () => {
      try {
        const status = await api.getServerStatus();
        if (alive) setTelemetry((current) => [...current.slice(-29), status]);
      } catch {
        // Readiness is also represented by the absence of new telemetry points.
      }
    };
    void sample();
    const timer = window.setInterval(() => void sample(), 2500);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [tab]);

  const activeLlm = llms.data?.find(
    (item) => item.id === runtime.data?.llm_preset_id,
  );
  const activePrompt = prompts.data?.find(
    (item) => item.id === runtime.data?.prompt_preset_id,
  );
  const activeEmbedding = embeddings.data?.find(
    (item) => item.id === runtime.data?.embedding_preset_id,
  );
  const currentStatus = telemetry.at(-1);

  const refreshPresets = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin-runtime"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-llms"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-prompts"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-prompt-capabilities"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-embeddings"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-audits"] }),
    ]);
  };

  function selectLlm(item: LlmPreset) {
    setSelectedLlmId(item.id);
    setLlmForm({
      name: item.name,
      base_url: item.base_url,
      api_key: "",
      model: item.model,
      parameters: JSON.stringify(item.parameters, null, 2),
      context_window_tokens: item.context_window_tokens,
      max_output_tokens: item.max_output_tokens,
      history_turn_limit: item.history_turn_limit,
      input_credits_per_million_tokens: Number(
        item.input_credits_per_million_tokens,
      ),
      output_credits_per_million_tokens: Number(
        item.output_credits_per_million_tokens,
      ),
      usage_mode: item.usage_mode,
      bound_prompt_preset_id: item.bound_prompt_preset_id ?? "",
      bound_embedding_preset_id: item.bound_embedding_preset_id ?? "",
    });
  }

  function selectPrompt(item: PromptPreset) {
    setSelectedPromptId(item.id);
    setPromptForm({
      name: item.name,
      description: item.description ?? "",
      capability: item.capability,
      variant_key: item.variant_key,
      messages: item.messages,
    });
    setActiveMessageIndex(0);
  }

  function selectEmbedding(item: EmbeddingPreset) {
    setSelectedEmbeddingId(item.id);
    setEmbeddingForm({
      name: item.name,
      provider: item.provider,
      base_url: item.base_url ?? "",
      api_key: "",
      model: item.model,
      dimensions: item.dimensions,
      parameters: JSON.stringify(item.parameters, null, 2),
    });
  }

  const saveLlm = useMutation({
    mutationFn: async () => {
      const sameName = llms.data?.find(
        (item) => item.name === llmForm.name.trim(),
      );
      if (
        sameName &&
        !window.confirm(`已存在“${sameName.name}”。覆盖这个预设吗？`)
      ) {
        throw new Error("SAVE_CANCELLED");
      }
      const payload = {
        ...llmForm,
        name: llmForm.name.trim(),
        api_key: llmForm.api_key || undefined,
        parameters: parseParameters(llmForm.parameters),
        bound_prompt_preset_id: llmForm.bound_prompt_preset_id || null,
        bound_embedding_preset_id: llmForm.bound_embedding_preset_id || null,
      };
      return sameName
        ? api.updateLlmPreset(sameName.id, payload)
        : api.createLlmPreset(payload);
    },
    onSuccess: async (item) => {
      selectLlm(item);
      setNotice(
        item.usage_mode === "estimated"
          ? "此渠道不返回usage"
          : `LLM 预设“${item.name}”已保存`,
      );
      await refreshPresets();
    },
    onError: (error) => {
      if (error instanceof Error && error.message === "SAVE_CANCELLED") return;
      setNotice(errorText(error));
    },
  });

  const savePrompt = useMutation({
    mutationFn: async () => {
      const messages = promptForm.messages.map((message, position) => ({
        ...message,
        position,
      }));
      return selectedPromptId
        ? api.updatePromptPreset(selectedPromptId, { ...promptForm, messages })
        : api.createPromptPreset({ ...promptForm, messages });
    },
    onSuccess: async (item) => {
      selectPrompt(item);
      setNotice(`提示词预设“${item.name}”已保存`);
      await refreshPresets();
    },
    onError: (error) => {
      if (error instanceof Error && error.message === "SAVE_CANCELLED") return;
      setNotice(errorText(error));
    },
  });

  const createCapability = useMutation({
    mutationFn: () =>
      api.createPromptCapability({
        key: capabilityForm.key.trim(),
        name: capabilityForm.name.trim(),
      }),
    onSuccess: async (item) => {
      setCapabilityForm({ key: "", name: "" });
      setPromptForm((current) => ({ ...current, capability: item.key }));
      setNotice(`功能“${item.name}”已创建`);
      await queryClient.invalidateQueries({
        queryKey: ["admin-prompt-capabilities"],
      });
    },
    onError: (error) => setNotice(errorText(error)),
  });

  const deleteCapability = useMutation({
    mutationFn: api.deletePromptCapability,
    onSuccess: async (_, deletedKey) => {
      setPromptForm((current) => ({
        ...current,
        capability:
          current.capability === deletedKey
            ? "report_generation"
            : current.capability,
      }));
      setNotice("功能已删除");
      await queryClient.invalidateQueries({
        queryKey: ["admin-prompt-capabilities"],
      });
    },
    onError: (error) => setNotice(errorText(error)),
  });

  const saveEmbedding = useMutation({
    mutationFn: async () => {
      const sameName = embeddings.data?.find(
        (item) => item.name === embeddingForm.name.trim(),
      );
      if (
        sameName &&
        !window.confirm(`已存在“${sameName.name}”。覆盖这个预设吗？`)
      ) {
        throw new Error("SAVE_CANCELLED");
      }
      const payload = {
        ...embeddingForm,
        name: embeddingForm.name.trim(),
        api_key: embeddingForm.api_key || undefined,
        base_url: embeddingForm.base_url || undefined,
        parameters: parseParameters(embeddingForm.parameters),
      };
      return sameName
        ? api.updateEmbeddingPreset(sameName.id, payload)
        : api.createEmbeddingPreset(payload);
    },
    onSuccess: async (item) => {
      selectEmbedding(item);
      setNotice(`Embedding 预设“${item.name}”已保存`);
      await refreshPresets();
    },
    onError: (error) => {
      if (error instanceof Error && error.message === "SAVE_CANCELLED") return;
      setNotice(errorText(error));
    },
  });

  const deletePreset = useMutation({
    mutationFn: async ({
      type,
      id,
    }: {
      type: "llm" | "prompt" | "embedding";
      id: string;
    }) => {
      if (type === "llm") return api.deleteLlmPreset(id);
      if (type === "prompt") return api.deletePromptPreset(id);
      return api.deleteEmbeddingPreset(id);
    },
    onSuccess: async () => {
      setSelectedLlmId("");
      setSelectedPromptId("");
      setSelectedEmbeddingId("");
      setNotice("预设已删除");
      await refreshPresets();
    },
    onError: (error) => setNotice(errorText(error)),
  });

  const saveGroup = useMutation({
    mutationFn: async () => {
      const terms = groupForm.terms
        .split(",")
        .map((term) => term.trim())
        .filter(Boolean);
      const sameName = groups.data?.find(
        (item) => item.name === groupForm.name.trim(),
      );
      const targetName = groupForm.originalName || sameName?.name;
      if (
        sameName &&
        !groupForm.originalName &&
        !window.confirm(`覆盖分组“${sameName.name}”吗？`)
      ) {
        throw new Error("SAVE_CANCELLED");
      }
      const payload = {
        name: groupForm.name.trim(),
        terms,
        enabled: groupForm.enabled,
      };
      return targetName
        ? api.updateSensitiveGroup(targetName, payload)
        : api.createSensitiveGroup(payload);
    },
    onSuccess: async (item) => {
      setGroupForm({
        originalName: item.name,
        name: item.name,
        terms: item.terms.join(", "),
        enabled: item.enabled,
      });
      setNotice(`敏感词分组“${item.name}”已保存`);
      await queryClient.invalidateQueries({
        queryKey: ["admin-sensitive-groups"],
      });
    },
    onError: (error) => {
      if (error instanceof Error && error.message === "SAVE_CANCELLED") return;
      setNotice(errorText(error));
    },
  });

  const deleteGroup = useMutation({
    mutationFn: api.deleteSensitiveGroup,
    onSuccess: async () => {
      setGroupForm({ originalName: "", name: "", terms: "", enabled: true });
      setNotice("敏感词分组已删除");
      await queryClient.invalidateQueries({
        queryKey: ["admin-sensitive-groups"],
      });
    },
    onError: (error) => setNotice(errorText(error)),
  });

  const updateUser = useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      status: "active" | "disabled";
    }) => api.updateAdminUser(id, { status }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (error) => setNotice(errorText(error)),
  });
  const updateUserQuota = useMutation({
    mutationFn: ({
      id,
      storageMb,
      monthlyCredits,
      grant,
    }: {
      id: string;
      storageMb: number;
      monthlyCredits: number;
      grant?: number;
    }) =>
      api.updateAdminUser(id, {
        storage_quota_bytes: Math.round(storageMb * 1024 * 1024),
        monthly_credits: monthlyCredits,
        ...(grant && grant > 0 ? { credit_grant: grant } : {}),
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (error) => setNotice(errorText(error)),
  });

  const promptTokenEstimate = useMemo(
    () =>
      Math.ceil(
        promptForm.messages.reduce(
          (sum, item) => sum + item.content.length,
          0,
        ) / 2.5,
      ),
    [promptForm.messages],
  );

  function moveMessage(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= promptForm.messages.length) return;
    setPromptForm((current) => {
      const messages = [...current.messages];
      [messages[index], messages[target]] = [messages[target], messages[index]];
      return { ...current, messages };
    });
    setActiveMessageIndex(target);
  }

  function updateMessage(index: number, patch: Partial<PromptMessage>) {
    setPromptForm((current) => ({
      ...current,
      messages: current.messages.map((message, itemIndex) =>
        itemIndex === index ? { ...message, ...patch } : message,
      ),
    }));
  }

  function confirmDelete(
    type: "llm" | "prompt" | "embedding",
    id: string,
    name: string,
  ) {
    if (window.confirm(`删除预设“${name}”？此操作无法撤销。`)) {
      deletePreset.mutate({ type, id });
    }
  }

  return (
    <main className="control-page">
      <header className="control-header">
        <button className="control-back" onClick={onBack} type="button">
          <ChevronLeft />
          返回研究工作台
        </button>
        <div className="control-title">
          <span>ADMINISTRATION / MVP 4</span>
          <h1>管理员控制台</h1>
        </div>
        <div
          className={`runtime-state source-${runtime.data?.source ?? "offline"}`}
        >
          <i />
          {runtime.data?.source === "database"
            ? "预设运行中"
            : "环境配置运行中"}
        </div>
      </header>

      {notice && (
        <button
          className="control-notice"
          onClick={() => setNotice(null)}
          type="button"
        >
          <span>{notice}</span>
          <X />
        </button>
      )}

      <div className="control-layout">
        <div className={`control-nav-wrapper ${sidebarCollapsed ? "collapsed" : "expanded"}`}>
          <button
            className="sidebar-toggle-handle"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
            type="button"
          >
            {sidebarCollapsed ? <ChevronRight /> : <ChevronLeft />}
          </button>
          <nav className="control-nav" aria-label="管理员功能">
            {[
              ["dashboard", CircleGauge, "仪表盘"],
              ["llm", KeyRound, "LLM 预设"],
              ["prompt", Braces, "提示词预设"],
              ["embedding", Database, "Embedding 预设"],
              ["safety", ShieldCheck, "敏感词"],
              ["templates", LayoutTemplate, "报告模板"],
              ["moderation", Gavel, "内容审核"],
              ["announcements", Megaphone, "校园公告"],
              ["users", Users, "用户与用量"],
              ["audit", FileClock, "审计记录"],
            ].map(([key, Icon, label]) => (
              <button
                className={tab === key ? "active" : ""}
                key={String(key)}
                onClick={() => setTab(key as AdminTab)}
                title={String(label)}
                type="button"
              >
                <Icon />
                <span>{String(label)}</span>
              </button>
            ))}
          </nav>
        </div>

        <section className="control-content">
          {tab === "dashboard" && (
            <Dashboard
              activeEmbedding={activeEmbedding}
              activeLlm={activeLlm}
              activePrompt={activePrompt}
              embeddings={embeddings.data ?? []}
              llms={llms.data ?? []}
              logs={logs.data ?? []}
              logLevel={logLevel}
              prompts={prompts.data ?? []}
              samples={telemetry}
              status={currentStatus}
              onEmbeddingChange={async (id) => {
                await api.activateEmbeddingPreset(id);
                await refreshPresets();
              }}
              onLlmChange={async (id) => {
                await api.activateLlmPreset(id, true);
                await refreshPresets();
              }}
              onLogLevelChange={setLogLevel}
              onPromptChange={async (id) => {
                await api.activatePromptPreset(id);
                await refreshPresets();
              }}
            />
          )}

          {tab === "llm" && (
            <PresetPage
              description="配置兼容接口、模型与请求参数。API Key 只写入，不会从服务端回显。"
              icon={<KeyRound />}
              title="LLM 预设"
            >
              <PresetSelector
                items={llms.data ?? []}
                selectedId={selectedLlmId}
                onCreate={() => {
                  setSelectedLlmId("");
                  setLlmForm(emptyLlmForm);
                  setModels([]);
                }}
                onDelete={(item) => confirmDelete("llm", item.id, item.name)}
                onSelect={(id) => {
                  const item = llms.data?.find((preset) => preset.id === id);
                  if (item) selectLlm(item);
                }}
              />
              <form
                className="preset-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  saveLlm.mutate();
                }}
              >
                <Field label="预设名称">
                  <input
                    required
                    value={llmForm.name}
                    onChange={(event) =>
                      setLlmForm({ ...llmForm, name: event.target.value })
                    }
                  />
                </Field>
                <Field label="端点（Base URL）" halfWide>
                  <input
                    required
                    placeholder="https://provider.example/v1"
                    value={llmForm.base_url}
                    onChange={(event) =>
                      setLlmForm({ ...llmForm, base_url: event.target.value })
                    }
                  />
                </Field>
                <Field label="API Key">
                  <input
                    type="password"
                    placeholder={
                      selectedLlmId ? "留空则保留原密钥" : "输入服务商密钥"
                    }
                    value={llmForm.api_key}
                    onChange={(event) =>
                      setLlmForm({ ...llmForm, api_key: event.target.value })
                    }
                  />
                </Field>
                <Field label="模型名">
                  <div className="input-action">
                    {models.length > 0 ? (
                      <select
                        required
                        value={llmForm.model}
                        onChange={(event) =>
                          setLlmForm({ ...llmForm, model: event.target.value })
                        }
                      >
                        {!models.includes(llmForm.model) && llmForm.model && (
                          <option value={llmForm.model}>
                            {llmForm.model} (当前设置)
                          </option>
                        )}
                        {models.map((model) => (
                          <option key={model} value={model}>
                            {model}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        required
                        placeholder="手动输入模型名，或点击右侧加载"
                        value={llmForm.model}
                        onChange={(event) =>
                          setLlmForm({ ...llmForm, model: event.target.value })
                        }
                      />
                    )}
                    <button
                      disabled={!selectedLlmId}
                      onClick={async () => {
                        try {
                          const result =
                            await api.fetchLlmModels(selectedLlmId);
                          setModels(result.models);
                          setNotice(`已加载 ${result.models.length} 个模型`);
                        } catch (error) {
                          setNotice(errorText(error));
                        }
                      }}
                      type="button"
                    >
                      <RefreshCw />
                      加载模型
                    </button>
                  </div>
                </Field>
                <Field label="上下文窗口 Tokens" halfWide>
                  <input
                    min={4096}
                    type="number"
                    value={llmForm.context_window_tokens}
                    onChange={(event) =>
                      setLlmForm({
                        ...llmForm,
                        context_window_tokens: Number(event.target.value),
                      })
                    }
                  />
                </Field>
                <Field label="最大输出 Tokens" halfWide>
                  <input
                    min={1}
                    type="number"
                    value={llmForm.max_output_tokens}
                    onChange={(event) =>
                      setLlmForm({
                        ...llmForm,
                        max_output_tokens: Number(event.target.value),
                      })
                    }
                  />
                </Field>
                <Field label="保留对话轮数">
                  <input
                    min={0}
                    max={100}
                    type="number"
                    value={llmForm.history_turn_limit}
                    onChange={(event) =>
                      setLlmForm({
                        ...llmForm,
                        history_turn_limit: Number(event.target.value),
                      })
                    }
                  />
                </Field>
                <Field label="usage 获取方式">
                  <select
                    value={llmForm.usage_mode}
                    onChange={(event) =>
                      setLlmForm({
                        ...llmForm,
                        usage_mode: event.target.value as typeof llmForm.usage_mode,
                      })
                    }
                  >
                    <option value="auto">自动检测</option>
                    <option value="reported">渠道返回</option>
                    <option value="estimated">估算</option>
                  </select>
                  {llmForm.usage_mode === "estimated" && (
                    <p className="mvp5-notice">此渠道不返回usage</p>
                  )}
                </Field>
                <Field label="输入 Credits / 百万 Tokens" halfWide>
                  <input
                    min={0}
                    step="0.000001"
                    type="number"
                    value={llmForm.input_credits_per_million_tokens}
                    onChange={(event) =>
                      setLlmForm({
                        ...llmForm,
                        input_credits_per_million_tokens: Number(event.target.value),
                      })
                    }
                  />
                </Field>
                <Field label="输出 Credits / 百万 Tokens" halfWide>
                  <input
                    min={0}
                    step="0.000001"
                    type="number"
                    value={llmForm.output_credits_per_million_tokens}
                    onChange={(event) =>
                      setLlmForm({
                        ...llmForm,
                        output_credits_per_million_tokens: Number(event.target.value),
                      })
                    }
                  />
                </Field>
                <Field
                  label="附加请求参数（JSON）"
                  help="可填写 temperature、max_tokens、top_p 等兼容参数。"
                  wide
                >
                  <textarea
                    rows={8}
                    value={llmForm.parameters}
                    onChange={(event) =>
                      setLlmForm({ ...llmForm, parameters: event.target.value })
                    }
                  />
                </Field>
                <Field label="切换时同步提示词">
                  <select
                    value={llmForm.bound_prompt_preset_id}
                    onChange={(event) =>
                      setLlmForm({
                        ...llmForm,
                        bound_prompt_preset_id: event.target.value,
                      })
                    }
                  >
                    <option value="">不绑定</option>
                    {prompts.data?.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="切换时同步 Embedding">
                  <select
                    value={llmForm.bound_embedding_preset_id}
                    onChange={(event) =>
                      setLlmForm({
                        ...llmForm,
                        bound_embedding_preset_id: event.target.value,
                      })
                    }
                  >
                    <option value="">不绑定</option>
                    {embeddings.data?.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <PresetActions
                  active={activeLlm?.id === selectedLlmId}
                  canActivate={Boolean(selectedLlmId)}
                  onActivate={async () => {
                    await api.activateLlmPreset(selectedLlmId, true);
                    await refreshPresets();
                  }}
                  onReset={() =>
                    selectedLlmId
                      ? selectLlm(
                          llms.data!.find((item) => item.id === selectedLlmId)!,
                        )
                      : setLlmForm(emptyLlmForm)
                  }
                />
              </form>
            </PresetPage>
          )}

          {tab === "prompt" && (
            <PresetPage
              description="勾选决定学生端可见范围；功能与风格均由这里统一发布。"
              icon={<Braces />}
              title="提示词预设"
            >
              <div className="prompt-library-layout">
                <aside className="prompt-library-sidebar">
                  <div className="safety-sidebar-header">
                    <span>预设目录</span>
                    <button
                      onClick={() => {
                        setSelectedPromptId("");
                        setPromptForm(emptyPromptForm);
                      }}
                      title="新建预设"
                      type="button"
                    >
                      <Plus />
                    </button>
                  </div>
                  <div className="prompt-preset-list">
                    {prompts.data?.map((item) => {
                      const capability = promptCapabilities.data?.find(
                        (entry) => entry.key === item.capability,
                      );
                      return (
                        <div
                          className={`prompt-preset-card ${
                            selectedPromptId === item.id ? "active" : ""
                          }`}
                          key={item.id}
                          onClick={() => selectPrompt(item)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              selectPrompt(item);
                            }
                          }}
                          role="button"
                          tabIndex={0}
                        >
                          <input
                            checked={item.is_active}
                            onClick={(event) => event.stopPropagation()}
                            onChange={async (event) => {
                              try {
                                await api.setPromptPresetEnabled(
                                  item.id,
                                  event.target.checked,
                                );
                                await refreshPresets();
                                await queryClient.invalidateQueries({
                                  queryKey: ["prompt-options"],
                                });
                              } catch (error) {
                                setNotice(errorText(error));
                              }
                            }}
                            title={
                              item.is_active
                                ? "已向学生端开放"
                                : "未向学生端开放"
                            }
                            type="checkbox"
                          />
                          <span className="prompt-card-copy">
                            <strong>{item.name}</strong>
                            <small>
                              {capability?.name ?? item.capability}
                              <i>·</i>
                              {item.variant_key}
                            </small>
                          </span>
                          <span className="prompt-card-version">
                            v{item.version}
                          </span>
                          <button
                            className="prompt-card-delete"
                            onClick={(event) => {
                              event.stopPropagation();
                              confirmDelete("prompt", item.id, item.name);
                            }}
                            title="删除预设"
                            type="button"
                          >
                            <Trash2 />
                          </button>
                        </div>
                      );
                    })}
                    {!prompts.data?.length && (
                      <p className="report-empty-copy">暂无提示词预设</p>
                    )}
                  </div>

                  <div className="capability-manager">
                    <div className="capability-manager-title">
                      <span>功能管理</span>
                      <small>三项系统功能不可删除</small>
                    </div>
                    <div className="capability-list">
                      {promptCapabilities.data?.map((item) => (
                        <div className="capability-row" key={item.key}>
                          <span>
                            <strong>{item.name}</strong>
                            <small>{item.key}</small>
                          </span>
                          {item.is_system ? (
                            <KeyRound aria-label="系统功能" />
                          ) : (
                            <button
                              disabled={deleteCapability.isPending}
                              onClick={() => {
                                if (
                                  window.confirm(
                                    `删除功能“${item.name}”？有关联预设时不能删除。`,
                                  )
                                ) {
                                  deleteCapability.mutate(item.key);
                                }
                              }}
                              title="删除功能"
                              type="button"
                            >
                              <Trash2 />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                    <form
                      className="capability-create-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        createCapability.mutate();
                      }}
                    >
                      <input
                        maxLength={80}
                        placeholder="功能名称"
                        required
                        value={capabilityForm.name}
                        onChange={(event) =>
                          setCapabilityForm({
                            ...capabilityForm,
                            name: event.target.value,
                          })
                        }
                      />
                      <input
                        maxLength={40}
                        pattern="[a-z][a-z0-9_]*"
                        placeholder="function_key"
                        required
                        value={capabilityForm.key}
                        onChange={(event) =>
                          setCapabilityForm({
                            ...capabilityForm,
                            key: event.target.value,
                          })
                        }
                      />
                      <button
                        disabled={createCapability.isPending}
                        type="submit"
                      >
                        添加功能
                      </button>
                    </form>
                  </div>
                </aside>

                <div className="prompt-editor">
                  <div className="preset-form prompt-meta-form">
                    <Field
                      headerExtra={
                        <span className="token-estimate-text">
                          约 {promptTokenEstimate} tokens
                        </span>
                      }
                      label="预设名称"
                      wide
                    >
                      <input
                        required
                        value={promptForm.name}
                        onChange={(event) =>
                          setPromptForm({
                            ...promptForm,
                            name: event.target.value,
                          })
                        }
                      />
                    </Field>
                    <Field label="功能" halfWide>
                      <select
                        value={promptForm.capability}
                        onChange={(event) =>
                          setPromptForm({
                            ...promptForm,
                            capability: event.target.value,
                          })
                        }
                      >
                        {promptCapabilities.data?.map((item) => (
                          <option key={item.key} value={item.key}>
                            {item.name}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="风格键" halfWide>
                      <input
                        pattern="[a-zA-Z0-9][a-zA-Z0-9_-]*"
                        required
                        value={promptForm.variant_key}
                        onChange={(event) =>
                          setPromptForm({
                            ...promptForm,
                            variant_key: event.target.value,
                          })
                        }
                      />
                    </Field>
                  </div>
                  <div className="macro-strip">
                    <span>插入宏</span>
                    {[
                      "{{topic}}",
                      "{{research_goal}}",
                      "{{section_title}}",
                      "{{section_instructions}}",
                      "{{evidence_json}}",
                      "{{user_input}}",
                      "{{inputs.topic}}",
                    ].map((macro) => (
                      <button
                        key={macro}
                        onClick={() => {
                          const message = promptForm.messages[activeMessageIndex];
                          if (message)
                            updateMessage(activeMessageIndex, {
                              content: `${message.content}${message.content ? "\n" : ""}${macro}`,
                            });
                        }}
                        type="button"
                      >
                        {macro}
                      </button>
                    ))}
                  </div>
                  <div className="message-list">
                    {promptForm.messages.map((message, index) => (
                      <article
                        className={`prompt-message role-${message.role} ${activeMessageIndex === index ? "active" : ""}`}
                        key={`${index}-${message.name}`}
                        onClick={() => setActiveMessageIndex(index)}
                      >
                        <div className="prompt-message-toolbar">
                          <input
                            value={message.name}
                            onChange={(event) =>
                              updateMessage(index, { name: event.target.value })
                            }
                          />
                          <select
                            value={message.role}
                            onChange={(event) =>
                              updateMessage(index, {
                                role: event.target.value as PromptMessage["role"],
                              })
                            }
                          >
                            <option value="system">系统</option>
                            <option value="user">用户</option>
                            <option value="assistant">AI 助手</option>
                          </select>
                          <label>
                            <input
                              checked={message.enabled}
                              onChange={(event) =>
                                updateMessage(index, {
                                  enabled: event.target.checked,
                                })
                              }
                              type="checkbox"
                            />
                            启用
                          </label>
                          <button
                            disabled={index === 0}
                            onClick={() => moveMessage(index, -1)}
                            type="button"
                          >
                            <ArrowUp />
                          </button>
                          <button
                            disabled={index === promptForm.messages.length - 1}
                            onClick={() => moveMessage(index, 1)}
                            type="button"
                          >
                            <ArrowDown />
                          </button>
                          <button
                            onClick={() =>
                              setPromptForm((current) => ({
                                ...current,
                                messages: current.messages.filter(
                                  (_, itemIndex) => itemIndex !== index,
                                ),
                              }))
                            }
                            type="button"
                          >
                            <Trash2 />
                          </button>
                        </div>
                        <textarea
                          rows={7}
                          value={message.content}
                          onChange={(event) =>
                            updateMessage(index, { content: event.target.value })
                          }
                        />
                      </article>
                    ))}
                  </div>
                  <button
                    className="add-message"
                    onClick={() =>
                      setPromptForm((current) => ({
                        ...current,
                        messages: [
                          ...current.messages,
                          emptyPromptMessage(current.messages.length),
                        ],
                      }))
                    }
                    type="button"
                  >
                    <Plus />
                    添加消息
                  </button>
                  <PresetActions
                    active={
                      prompts.data?.find((item) => item.id === selectedPromptId)
                        ?.is_active ?? false
                    }
                    canActivate={false}
                    onActivate={() => undefined}
                    onReset={() =>
                      selectedPromptId
                        ? selectPrompt(
                            prompts.data!.find(
                              (item) => item.id === selectedPromptId,
                            )!,
                          )
                        : setPromptForm(emptyPromptForm)
                    }
                    onSave={() => savePrompt.mutate()}
                  />
                </div>
              </div>
            </PresetPage>
          )}

          {tab === "embedding" && (
            <PresetPage
              description="选择本地基线或第三方兼容向量接口；切换维度后需要重建既有文献向量。"
              icon={<Database />}
              title="Embedding 预设"
            >
              <PresetSelector
                items={embeddings.data ?? []}
                selectedId={selectedEmbeddingId}
                onCreate={() => {
                  setSelectedEmbeddingId("");
                  setEmbeddingForm(emptyEmbeddingForm);
                }}
                onDelete={(item) =>
                  confirmDelete("embedding", item.id, item.name)
                }
                onSelect={(id) => {
                  const item = embeddings.data?.find(
                    (preset) => preset.id === id,
                  );
                  if (item) selectEmbedding(item);
                }}
              />
              <form
                className="preset-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  saveEmbedding.mutate();
                }}
              >
                <Field label="预设名称">
                  <input
                    required
                    value={embeddingForm.name}
                    onChange={(event) =>
                      setEmbeddingForm({
                        ...embeddingForm,
                        name: event.target.value,
                      })
                    }
                  />
                </Field>
                <Field label="提供方式">
                  <select
                    value={embeddingForm.provider}
                    onChange={(event) =>
                      setEmbeddingForm({
                        ...embeddingForm,
                        provider: event.target
                          .value as typeof embeddingForm.provider,
                      })
                    }
                  >
                    <option value="local_hashing">本地哈希基线</option>
                    <option value="openai_compatible">第三方兼容接口</option>
                  </select>
                </Field>
                <Field label="端点（Base URL）" halfWide>
                  <input
                    disabled={embeddingForm.provider === "local_hashing"}
                    value={embeddingForm.base_url}
                    onChange={(event) =>
                      setEmbeddingForm({
                        ...embeddingForm,
                        base_url: event.target.value,
                      })
                    }
                  />
                </Field>
                <Field label="API Key">
                  <input
                    disabled={embeddingForm.provider === "local_hashing"}
                    type="password"
                    placeholder={selectedEmbeddingId ? "留空则保留原密钥" : ""}
                    value={embeddingForm.api_key}
                    onChange={(event) =>
                      setEmbeddingForm({
                        ...embeddingForm,
                        api_key: event.target.value,
                      })
                    }
                  />
                </Field>
                <Field label="模型名">
                  <input
                    required
                    value={embeddingForm.model}
                    onChange={(event) =>
                      setEmbeddingForm({
                        ...embeddingForm,
                        model: event.target.value,
                      })
                    }
                  />
                </Field>
                <Field label="向量维度">
                  <input
                    min={8}
                    max={16000}
                    type="number"
                    value={embeddingForm.dimensions}
                    onChange={(event) =>
                      setEmbeddingForm({
                        ...embeddingForm,
                        dimensions: Number(event.target.value),
                      })
                    }
                  />
                </Field>
                <Field label="附加请求参数（JSON）" wide>
                  <textarea
                    rows={6}
                    value={embeddingForm.parameters}
                    onChange={(event) =>
                      setEmbeddingForm({
                        ...embeddingForm,
                        parameters: event.target.value,
                      })
                    }
                  />
                </Field>
                <PresetActions
                  active={activeEmbedding?.id === selectedEmbeddingId}
                  canActivate={Boolean(selectedEmbeddingId)}
                  onActivate={async () => {
                    await api.activateEmbeddingPreset(selectedEmbeddingId);
                    await refreshPresets();
                  }}
                  onReset={() =>
                    selectedEmbeddingId
                      ? selectEmbedding(
                          embeddings.data!.find(
                            (item) => item.id === selectedEmbeddingId,
                          )!,
                        )
                      : setEmbeddingForm(emptyEmbeddingForm)
                  }
                />
                {activeEmbedding?.id === selectedEmbeddingId && (
                  <button
                    className="reindex-action"
                    onClick={async () => {
                      const result =
                        await api.reindexEmbeddingPreset(selectedEmbeddingId);
                      setNotice(
                        `已安排 ${result.queued_documents} 篇文献重建向量`,
                      );
                    }}
                    type="button"
                  >
                    <RefreshCw />
                    重建全部文献向量
                  </button>
                )}
              </form>
            </PresetPage>
          )}

          {tab === "safety" && (
            <PresetPage
              description="每个分组独立启用；词项使用英文半角逗号分隔。"
              icon={<ShieldCheck />}
              title="敏感词分组"
            >
              <div className="safety-layout">
                <aside className="safety-sidebar">
                  <div className="safety-sidebar-header">
                    <span>分组列表</span>
                    <button
                      onClick={() =>
                        setGroupForm({
                          originalName: "",
                          name: "",
                          terms: "",
                          enabled: true,
                        })
                      }
                      title="新建分组"
                      type="button"
                    >
                      <Plus className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <div className="safety-group-list">
                    {groups.data?.map((group) => (
                      <div
                        className={`safety-group-item ${groupForm.originalName === group.name ? "active" : ""}`}
                        key={group.name}
                        onClick={() =>
                          setGroupForm({
                            originalName: group.name,
                            name: group.name,
                            terms: group.terms.join(", "),
                            enabled: group.enabled,
                          })
                        }
                      >
                        <input
                          checked={group.enabled}
                          onChange={async (e) => {
                            e.stopPropagation();
                            try {
                              await api.updateSensitiveGroup(group.name, {
                                name: group.name,
                                terms: group.terms,
                                enabled: e.target.checked,
                              });
                              if (groupForm.originalName === group.name) {
                                setGroupForm((prev) => ({
                                  ...prev,
                                  enabled: e.target.checked,
                                }));
                              }
                              await queryClient.invalidateQueries({
                                queryKey: ["admin-sensitive-groups"],
                              });
                            } catch (error) {
                              setNotice(errorText(error));
                            }
                          }}
                          type="checkbox"
                          title={group.enabled ? "已启用" : "已停用"}
                        />
                        <span className="group-name">{group.name}</span>
                        <span
                          className={`group-status-badge ${
                            group.enabled ? "active" : "disabled"
                          }`}
                        >
                          {group.enabled ? "已启用" : "已停用"}
                        </span>
                        <button
                          className="group-delete-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (window.confirm(`删除分组“${group.name}”？`)) {
                              deleteGroup.mutate(group.name);
                            }
                          }}
                          title="删除分组"
                          type="button"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                    {!groups.data?.length && (
                      <p className="report-empty-copy">暂无敏感词分组</p>
                    )}
                  </div>
                </aside>
                <div className="safety-editor">
                  <form
                    className="preset-form group-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      saveGroup.mutate();
                    }}
                  >
                    <Field label="分组标题" wide>
                      <input
                        required
                        value={groupForm.name}
                        onChange={(event) =>
                          setGroupForm({ ...groupForm, name: event.target.value })
                        }
                      />
                    </Field>
                    <Field
                      label="敏感词"
                      help="例如：涉密词一, 涉密词二, 不规范表述"
                      wide
                    >
                      <textarea
                        rows={12}
                        required
                        value={groupForm.terms}
                        onChange={(event) =>
                          setGroupForm({ ...groupForm, terms: event.target.value })
                        }
                      />
                    </Field>
                    <PresetActions
                      active={false}
                      canActivate={false}
                      onActivate={() => undefined}
                      onReset={() =>
                        setGroupForm({
                          originalName: "",
                          name: "",
                          terms: "",
                          enabled: true,
                        })
                      }
                      onSave={() => saveGroup.mutate()}
                      saveLabel="保存分组"
                    />
                  </form>
                </div>
              </div>
            </PresetPage>
          )}

          {tab === "users" && (
            <UserTable
              users={users.data ?? []}
              onToggle={(id, status) => updateUser.mutate({ id, status })}
              onQuota={(id, storageMb, monthlyCredits, grant) =>
                updateUserQuota.mutate({ id, storageMb, monthlyCredits, grant })
              }
            />
          )}
          {tab === "templates" && <TemplateManagement />}
          {tab === "moderation" && <ModerationManagement />}
          {tab === "announcements" && <AnnouncementManagement />}
          {tab === "audit" && (
            <AuditTable
              items={audits.data ?? []}
              filters={auditFilters}
              users={users.data ?? []}
              onFilters={setAuditFilters}
            />
          )}
        </section>
      </div>
    </main>
  );
}

function PresetPage({
  title,
  description,
  icon,
  children,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="preset-page">
      <div className="preset-page-heading">
        <span>{icon}</span>
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function PresetSelector<T extends { id: string; name: string }>({
  items,
  selectedId,
  onSelect,
  onCreate,
  onDelete,
  extra,
}: {
  items: T[];
  selectedId: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (item: T) => void;
  extra?: React.ReactNode;
}) {
  const selected = items.find((item) => item.id === selectedId);
  return (
    <div className="preset-selector">
      <label>
        <span>当前编辑的预设</span>
        <select
          value={selectedId}
          onChange={(event) => onSelect(event.target.value)}
        >
          <option value="">新预设（尚未保存）</option>
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <button
        className="selector-icon"
        onClick={onCreate}
        title="新建预设"
        type="button"
      >
        <Plus />
      </button>
      <button
        className="selector-icon danger"
        disabled={!selected}
        onClick={() => selected && onDelete(selected)}
        title="删除预设"
        type="button"
      >
        <Trash2 />
      </button>
      {extra}
    </div>
  );
}

function Field({
  label,
  headerExtra,
  help,
  wide,
  halfWide,
  children,
}: {
  label: string;
  headerExtra?: React.ReactNode;
  help?: string;
  wide?: boolean;
  halfWide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label
      className={`preset-field ${wide ? "wide" : ""} ${
        halfWide ? "halfWide" : ""
      }`}
    >
      {headerExtra ? (
        <span className="preset-field-label">
          <span>{label}</span>
          {headerExtra}
        </span>
      ) : (
        <span>{label}</span>
      )}
      {children}
      {help && <small>{help}</small>}
    </label>
  );
}

function PresetActions({
  active,
  canActivate,
  onActivate,
  onReset,
  onSave,
  saveLabel = "保存当前预设",
}: {
  active: boolean;
  canActivate: boolean;
  onActivate: () => void;
  onReset: () => void;
  onSave?: () => void;
  saveLabel?: string;
}) {
  return (
    <div className="preset-actions">
      <button className="secondary-action" onClick={onReset} type="button">
        放弃修改
      </button>
      {canActivate && (
        <button
          className="secondary-action"
          disabled={active}
          onClick={onActivate}
          type="button"
        >
          {active ? "当前正在使用" : "设为当前预设"}
        </button>
      )}
      <button
        className="save-action"
        onClick={onSave}
        type={onSave ? "button" : "submit"}
      >
        <Save />
        {saveLabel}
      </button>
    </div>
  );
}

function Dashboard({
  llms,
  prompts,
  embeddings,
  activeLlm,
  activePrompt,
  activeEmbedding,
  status,
  samples,
  logs,
  logLevel,
  onLlmChange,
  onPromptChange,
  onEmbeddingChange,
  onLogLevelChange,
}: {
  llms: LlmPreset[];
  prompts: PromptPreset[];
  embeddings: EmbeddingPreset[];
  activeLlm?: LlmPreset;
  activePrompt?: PromptPreset;
  activeEmbedding?: EmbeddingPreset;
  status?: ServerStatus;
  samples: ServerStatus[];
  logs: ApplicationLog[];
  logLevel: string;
  onLlmChange: (id: string) => Promise<void>;
  onPromptChange: (id: string) => Promise<void>;
  onEmbeddingChange: (id: string) => Promise<void>;
  onLogLevelChange: (value: string) => void;
}) {
  return (
    <div className="dashboard-grid">
      <section className="dashboard-card runtime-card">
        <div className="dashboard-card-heading">
          <div>
            <span>RUNTIME PRESETS</span>
            <h2>预设配置</h2>
          </div>
          <Activity />
        </div>
        <div className="runtime-selectors">
          <Field label="LLM 预设">
            <select
              value={activeLlm?.id ?? ""}
              onChange={(event) => {
                if (event.target.value) void onLlmChange(event.target.value);
              }}
            >
              <option value="">环境配置</option>
              {llms.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="提示词预设">
            <select
              value={activePrompt?.id ?? ""}
              onChange={(event) => {
                if (event.target.value) void onPromptChange(event.target.value);
              }}
            >
              <option value="">模板默认提示词</option>
              {prompts.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Embedding 预设">
            <select
              value={activeEmbedding?.id ?? ""}
              onChange={(event) => {
                if (event.target.value)
                  void onEmbeddingChange(event.target.value);
              }}
            >
              <option value="">本地默认向量</option>
              {embeddings.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </section>
      <section className="dashboard-card telemetry-card">
        <div className="dashboard-card-heading">
          <div>
            <span>SERVER TELEMETRY</span>
            <h2>服务器状态</h2>
          </div>
          <Server />
        </div>
        <div className="telemetry-summary">
          <div>
            <i className="cpu-dot" />
            <span>CPU</span>
            <strong>{status?.cpu_percent.toFixed(1) ?? "—"}%</strong>
          </div>
          <div>
            <i className="memory-dot" />
            <span>内存</span>
            <strong>{status?.memory_percent.toFixed(1) ?? "—"}%</strong>
          </div>
          <div>
            <span>服务进程</span>
            <strong>
              {status ? formatBytes(status.process_rss_bytes) : "—"}
            </strong>
          </div>
        </div>
        <TelemetryChart samples={samples} />
      </section>
      <section className="dashboard-card log-card">
        <div className="dashboard-card-heading">
          <div>
            <span>APPLICATION STREAM</span>
            <h2>运行日志</h2>
          </div>
          <select
            value={logLevel}
            onChange={(event) => onLogLevelChange(event.target.value)}
          >
            <option value="">全部级别</option>
            <option value="ERROR">Error</option>
            <option value="WARNING">Warning</option>
            <option value="INFO">Info</option>
          </select>
        </div>
        <div className="log-stream">
          {logs.length ? (
            logs.map((item, index) => (
              <div
                className={`log-row level-${item.level.toLowerCase()}`}
                key={`${item.timestamp}-${index}`}
              >
                <time>{new Date(item.timestamp).toLocaleTimeString()}</time>
                <b>{item.level}</b>
                <span>{item.message}</span>
              </div>
            ))
          ) : (
            <p className="empty-log">尚无符合筛选条件的日志。</p>
          )}
        </div>
      </section>
    </div>
  );
}

function UserTable({
  users,
  onToggle,
  onQuota,
}: {
  users: Awaited<ReturnType<typeof api.listAdminUsers>>;
  onToggle: (id: string, status: "active" | "disabled") => void;
  onQuota: (
    id: string,
    storageMb: number,
    monthlyCredits: number,
    grant?: number,
  ) => void;
}) {
  return (
    <section className="data-panel">
      <div className="preset-page-heading">
        <span>
          <Users />
        </span>
        <div>
          <h2>用户与用量</h2>
          <p>查看硬盘与 Credits 用量，调整学生账号配额。</p>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>用户</th>
            <th>角色</th>
            <th>文献</th>
            <th>报告</th>
            <th>硬盘</th>
            <th>Credits</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {users.map((item) => (
            <tr key={item.id}>
              <td>
                <strong>{item.display_name}</strong>
                <small>{item.email}</small>
              </td>
              <td>{item.role}</td>
              <td>{item.document_count}</td>
              <td>{item.report_count}</td>
              <td>
                {item.role === "admin"
                  ? "不限"
                  : `${formatBytes(item.storage_used_bytes)} / ${formatBytes(item.storage_quota_bytes ?? 0)}`}
              </td>
              <td>
                {item.role === "admin"
                  ? "不限"
                  : `${Number(item.credit_balance ?? 0).toFixed(2)} / ${Number(item.monthly_credits ?? 0).toFixed(0)}`}
              </td>
              <td>
                <span
                  className={`status-badge ${
                    item.status === "active" ? "active" : "disabled"
                  }`}
                >
                  {item.status === "active" ? "启用" : "禁用"}
                </span>
              </td>
              <td>
                {item.role === "student" && (
                  <button
                    className="user-action-btn"
                    onClick={() => {
                      const storage = window.prompt(
                        "硬盘配额（MiB）",
                        String((item.storage_quota_bytes ?? 0) / 1024 / 1024),
                      );
                      if (storage === null) return;
                      const monthly = window.prompt(
                        "每月 Credits",
                        String(item.monthly_credits ?? 300),
                      );
                      if (monthly === null) return;
                      const grant = window.prompt("本期一次性增发 Credits（可为 0）", "0");
                      if (grant === null) return;
                      onQuota(
                        item.id,
                        Number(storage),
                        Number(monthly),
                        Number(grant),
                      );
                    }}
                    type="button"
                  >
                    调整配额
                  </button>
                )}
                <button
                  className={`user-action-btn ${
                    item.status === "active" ? "disable" : "enable"
                  }`}
                  disabled={item.role === "admin"}
                  onClick={() =>
                    onToggle(
                      item.id,
                      item.status === "active" ? "disabled" : "active",
                    )
                  }
                  type="button"
                >
                  {item.status === "active" ? "禁用" : "启用"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function AuditTable({
  items,
  filters,
  users,
  onFilters,
}: {
  items: Awaited<ReturnType<typeof api.listAuditLogs>>;
  filters: {
    action: string;
    actor_user_id: string;
    start_at: string;
    end_at: string;
  };
  users: Awaited<ReturnType<typeof api.listAdminUsers>>;
  onFilters: (value: {
    action: string;
    actor_user_id: string;
    start_at: string;
    end_at: string;
  }) => void;
}) {
  return (
    <section className="data-panel">
      <div className="preset-page-heading audit-panel-heading">
        <span>
          <FileClock />
        </span>
        <div>
          <h2>审计记录</h2>
          <p>追踪管理员对用户、预设和敏感词分组的修改。</p>
        </div>
        <div className="grid gap-2">
          <input placeholder="按动作筛选" value={filters.action} onChange={(event) => onFilters({ ...filters, action: event.target.value })} />
          <select value={filters.actor_user_id} onChange={(event) => onFilters({ ...filters, actor_user_id: event.target.value })}>
            <option value="">全部操作者</option>
            {users.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
          </select>
          <input type="datetime-local" value={filters.start_at} onChange={(event) => onFilters({ ...filters, start_at: event.target.value })} />
          <input type="datetime-local" value={filters.end_at} onChange={(event) => onFilters({ ...filters, end_at: event.target.value })} />
          <button onClick={() => void api.exportAuditLogs({
            ...filters,
            start_at: filters.start_at ? new Date(filters.start_at).toISOString() : undefined,
            end_at: filters.end_at ? new Date(filters.end_at).toISOString() : undefined,
          })}>导出 CSV</button>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>操作者</th>
            <th>动作</th>
            <th>对象</th>
            <th>结果</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{new Date(item.created_at).toLocaleString()}</td>
              <td>{item.actor_display_name ?? "系统"}</td>
              <td>
                <code>{item.action}</code>
              </td>
              <td>
                {item.target_type}
                <small>{item.target_id}</small>
              </td>
              <td>{item.result}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
