import type { ApiError, HealthResponse } from "@/contracts/api";

export class ApiClientError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: ApiError,
  ) {
    super(payload.error.message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const payload = (await response.json()) as ApiError;
    throw new ApiClientError(response.status, payload);
  }

  return (await response.json()) as T;
}

export const api = {
  getLiveness: () => request<HealthResponse>("/api/v1/health/live"),
  getReadiness: () => request<HealthResponse>("/api/v1/health/ready"),
};
