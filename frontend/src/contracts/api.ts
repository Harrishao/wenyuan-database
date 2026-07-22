export type HealthStatus = "ok" | "degraded";

export interface HealthResponse {
  name: string;
  environment: string;
  status: HealthStatus;
  version: string;
  services: Record<string, string>;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown> | null;
    request_id: string | null;
  };
}
