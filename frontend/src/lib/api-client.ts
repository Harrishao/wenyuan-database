import type {
  ApiError,
  AuthResponse,
  DocumentRecord,
  HealthResponse,
  KnowledgeBase,
  ReportCreateResponse,
  ReportDetail,
  ReportEvent,
  ReportListItem,
  ReportTemplate,
  ReportVersion,
  SearchResponse,
  UploadResponse,
  User,
} from "@/contracts/api";

export class ApiClientError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: ApiError,
  ) {
    super(payload.error.message);
  }
}

let accessToken: string | null = null;
let refreshPromise: Promise<AuthResponse> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    return (await response.json()) as ApiError;
  } catch {
    return {
      error: {
        code: "HTTP_ERROR",
        message: `请求失败（${response.status}）`,
        details: null,
        request_id: response.headers.get("X-Request-ID"),
      },
    };
  }
}

async function refreshAccessToken(): Promise<AuthResponse> {
  refreshPromise ??= fetch("/api/v1/auth/refresh", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json" },
  })
    .then(async (response) => {
      if (!response.ok) throw new ApiClientError(response.status, await parseError(response));
      const auth = (await response.json()) as AuthResponse;
      setAccessToken(auth.access_token);
      return auth;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

async function request<T>(path: string, init?: RequestInit, allowRefresh = true): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...init?.headers,
    },
  });

  const isCredentialEndpoint = ["/auth/login", "/auth/register", "/auth/refresh"].some((suffix) =>
    path.endsWith(suffix),
  );
  if (response.status === 401 && allowRefresh && !isCredentialEndpoint) {
    await refreshAccessToken();
    return request<T>(path, init, false);
  }
  if (!response.ok) {
    const payload = await parseError(response);
    throw new ApiClientError(response.status, payload);
  }

  if (response.status === 204) return undefined as T;

  return (await response.json()) as T;
}

function jsonRequest<T>(path: string, method: string, body?: unknown) {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const api = {
  getLiveness: () => request<HealthResponse>("/api/v1/health/live"),
  getReadiness: () => request<HealthResponse>("/api/v1/health/ready"),
  register: (payload: { email: string; password: string; display_name: string }) =>
    jsonRequest<AuthResponse>("/api/v1/auth/register", "POST", payload),
  login: (payload: { email: string; password: string }) =>
    jsonRequest<AuthResponse>("/api/v1/auth/login", "POST", payload),
  refresh: () => refreshAccessToken(),
  me: () => request<User>("/api/v1/auth/me"),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }, false),
  listKnowledgeBases: () => request<KnowledgeBase[]>("/api/v1/knowledge-bases"),
  createKnowledgeBase: (payload: { name: string; description?: string }) =>
    jsonRequest<KnowledgeBase>("/api/v1/knowledge-bases", "POST", payload),
  updateKnowledgeBase: (id: string, payload: { name?: string; description?: string }) =>
    jsonRequest<KnowledgeBase>(`/api/v1/knowledge-bases/${id}`, "PATCH", payload),
  deleteKnowledgeBase: (id: string) =>
    request<void>(`/api/v1/knowledge-bases/${id}`, { method: "DELETE" }),
  listDocuments: (knowledgeBaseId: string, query = "") =>
    request<DocumentRecord[]>(
      `/api/v1/knowledge-bases/${knowledgeBaseId}/documents${query ? `?query=${encodeURIComponent(query)}` : ""}`,
    ),
  uploadDocument: (knowledgeBaseId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<UploadResponse>(`/api/v1/knowledge-bases/${knowledgeBaseId}/documents`, {
      method: "POST",
      body: form,
    });
  },
  deleteDocument: (knowledgeBaseId: string, documentId: string) =>
    request<void>(`/api/v1/knowledge-bases/${knowledgeBaseId}/documents/${documentId}`, {
      method: "DELETE",
    }),
  retryDocument: (knowledgeBaseId: string, documentId: string) =>
    request(`/api/v1/knowledge-bases/${knowledgeBaseId}/documents/${documentId}/retry`, {
      method: "POST",
    }),
  searchKnowledgeBase: (knowledgeBaseId: string, query: string, topK = 6) =>
    jsonRequest<SearchResponse>(`/api/v1/knowledge-bases/${knowledgeBaseId}/search`, "POST", {
      query,
      top_k: topK,
    }),
  listReportTemplates: () => request<ReportTemplate[]>("/api/v1/report-templates"),
  listReports: (query = "") =>
    request<ReportListItem[]>(
      `/api/v1/reports${query ? `?query=${encodeURIComponent(query)}` : ""}`,
    ),
  createReport: (payload: {
    knowledge_base_id: string;
    template_key: string;
    title: string;
    inputs: Record<string, string>;
  }) => jsonRequest<ReportCreateResponse>("/api/v1/reports", "POST", payload),
  getReport: (id: string) => request<ReportDetail>(`/api/v1/reports/${id}`),
  updateReportSection: (reportId: string, sectionKey: string, content_markdown: string) =>
    jsonRequest<ReportDetail>(`/api/v1/reports/${reportId}/sections/${sectionKey}`, "PATCH", {
      content_markdown,
    }),
  retryReportSection: (reportId: string, sectionKey: string) =>
    jsonRequest<ReportCreateResponse>(
      `/api/v1/reports/${reportId}/sections/${sectionKey}/retry`,
      "POST",
      { reason: "generation_retry" },
    ),
  listReportVersions: (reportId: string) =>
    request<ReportVersion[]>(`/api/v1/reports/${reportId}/versions`),
  restoreReportVersion: (reportId: string, version: number) =>
    request<ReportDetail>(`/api/v1/reports/${reportId}/versions/${version}/restore`, {
      method: "POST",
    }),
  exportReport: async (reportId: string, title: string) => {
    const response = await authorizedFetch(`/api/v1/reports/${reportId}/export.docx`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${title}.docx`;
    anchor.click();
    URL.revokeObjectURL(url);
  },
};

async function authorizedFetch(path: string, init?: RequestInit, allowRefresh = true) {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...init?.headers,
    },
  });
  if (response.status === 401 && allowRefresh) {
    await refreshAccessToken();
    return authorizedFetch(path, init, false);
  }
  if (!response.ok) throw new ApiClientError(response.status, await parseError(response));
  return response;
}

export async function streamReportEvents(
  reportId: string,
  onEvent: (event: ReportEvent) => void,
  signal: AbortSignal,
) {
  const response = await authorizedFetch(`/api/v1/reports/${reportId}/events`, { signal });
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const data = frame
        .split("\n")
        .find((line) => line.startsWith("data: "))
        ?.slice(6);
      if (data && data !== "{}") onEvent(JSON.parse(data) as ReportEvent);
    }
  }
}
