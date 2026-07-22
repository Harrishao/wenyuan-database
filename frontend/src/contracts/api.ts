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

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: "student" | "admin";
  status: "active" | "disabled";
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export type ProcessingStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";

export interface DocumentRecord {
  id: string;
  knowledge_base_id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  status: ProcessingStatus;
  summary: string | null;
  keywords: string[];
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface UploadResponse {
  document: DocumentRecord;
  job_id: string;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  document_name: string;
  content: string;
  heading: string | null;
  page_number: number | null;
  similarity: number;
}

export interface SearchResponse {
  query: string;
  embedding_model: string;
  results: SearchResult[];
}
