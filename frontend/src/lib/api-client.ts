import type {
  ApiError,
  AuthResponse,
  DocumentRecord,
  HealthResponse,
  KnowledgeBase,
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
};
