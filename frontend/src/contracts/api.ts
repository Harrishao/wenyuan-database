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

export type ReportStatus = "draft" | "generating" | "ready" | "failed" | "archived";

export interface ReportTemplateSection {
  key: string;
  title: string;
  position: number;
  instructions: string;
  required_inputs: string[];
}

export interface ReportTemplate {
  id: string;
  key: string;
  name: string;
  description: string | null;
  version_id: string;
  version: number;
  required_inputs: string[];
  sections: ReportTemplateSection[];
}

export interface ReportCitation {
  id: string;
  marker: string;
  document_name: string;
  content: string;
  heading: string | null;
  page_number: number | null;
}

export interface ReportSection {
  id: string;
  key: string;
  title: string;
  position: number;
  content_markdown: string;
  status: ProcessingStatus;
  citations: ReportCitation[];
}

export interface ReportListItem {
  id: string;
  title: string;
  status: ReportStatus;
  template_name: string;
  knowledge_base_name: string;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface ReportDetail extends ReportListItem {
  inputs: Record<string, string>;
  progress: number;
  sections: ReportSection[];
}

export interface ReportCreateResponse {
  report: ReportDetail;
  job_id: string;
}

export interface ReportVersion {
  id: string;
  version: number;
  reason: string;
  content_markdown: string;
  created_at: string;
}

export interface ReportEvent {
  report_id: string;
  report_status: ReportStatus;
  job_status: ProcessingStatus | null;
  progress: number;
  current_section: string | null;
  completed_sections: string[];
  error_message: string | null;
}

export type PolishStyle = "academic" | "plain" | "concise";
export type AssistantRole = "rigorous_mentor" | "data_analyst";
export type AssistantMode = "dialogue" | "revision";

export interface SimilarityMatch {
  id: string;
  document_chunk_id: string;
  document_name: string;
  heading: string | null;
  page_number: number | null;
  source_text: string;
  matched_text: string;
  score: number;
  start_offset: number;
  end_offset: number;
}

export interface SimilarityResult {
  id: string;
  report_version: number;
  status: ProcessingStatus;
  overall_ratio: number;
  metric_label: string;
  parameters: {
    algorithm: string;
    threshold: number;
    ngram_range: [number, number];
    min_sentence_chars: number;
  };
  matches: SimilarityMatch[];
}

export interface PolishPreview {
  section_key: string;
  style: PolishStyle;
  original_text: string;
  polished_text: string;
  model: string;
}

export interface AssistantEvidence {
  marker: string;
  document_chunk_id: string;
  document_name: string;
  content: string;
  heading: string | null;
  page_number: number | null;
}

export interface AssistantAnswer {
  role: AssistantRole;
  mode: AssistantMode;
  answer: string;
  model: string;
  evidence: AssistantEvidence[];
}
