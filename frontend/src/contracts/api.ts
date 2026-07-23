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
  avatar_url: string | null;
  bio: string | null;
  email_verified: boolean;
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

export type ProcessingStatus =
  "pending" | "running" | "succeeded" | "failed" | "cancelled";

export interface DocumentRecord {
  id: string;
  knowledge_base_id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  status: ProcessingStatus;
  summary: string | null;
  keywords: string[];
  sensitive_hits: Array<Record<string, unknown>>;
  author: string | null;
  publication_title: string | null;
  publication_year: number | null;
  source: string | null;
  category: string | null;
  tags: string[];
  moderation_status: "pending" | "approved" | "restricted" | "removed";
  moderation_note: string | null;
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

export type ReportStatus =
  "draft" | "generating" | "ready" | "failed" | "archived";

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
  sensitive_hits: Array<Record<string, unknown>>;
  moderation_status: "pending" | "approved" | "restricted" | "removed";
  moderation_note: string | null;
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

export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  role: "student" | "admin";
  status: "active" | "disabled";
  document_count: number;
  report_count: number;
  created_at: string;
}

export interface PromptMessage {
  name: string;
  role: "system" | "user" | "assistant";
  content: string;
  enabled: boolean;
  position: number;
}

export interface PromptPreset {
  id: string;
  name: string;
  description: string | null;
  messages: PromptMessage[];
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LlmPreset {
  id: string;
  name: string;
  base_url: string;
  model: string;
  parameters: Record<string, unknown>;
  has_api_key: boolean;
  version: number;
  is_active: boolean;
  bound_prompt_preset_id: string | null;
  bound_embedding_preset_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmbeddingPreset {
  id: string;
  name: string;
  provider: "local_hashing" | "openai_compatible";
  base_url: string | null;
  model: string;
  dimensions: number;
  parameters: Record<string, unknown>;
  has_api_key: boolean;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RuntimeConfig {
  llm_preset_id: string | null;
  prompt_preset_id: string | null;
  embedding_preset_id: string | null;
  source: "database" | "environment" | "offline";
}

export interface SensitiveTerm {
  id: string;
  term: string;
  category: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface SensitiveGroup {
  name: string;
  terms: string[];
  enabled: boolean;
  count: number;
}

export interface ServerStatus {
  cpu_percent: number;
  memory_percent: number;
  memory_used_bytes: number;
  memory_total_bytes: number;
  process_rss_bytes: number;
  uptime_seconds: number;
  sampled_at: string;
}

export interface ApplicationLog {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  request_id: string | null;
}

export interface AuditLog {
  id: string;
  actor_user_id: string | null;
  actor_display_name: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  result: string;
  details: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
}

export interface UsageSummary {
  document_count: number;
  report_count: number;
  knowledge_base_count: number;
  storage_bytes: number;
  model_call_count: number;
}

export interface AdminTemplateSection {
  key: string;
  title: string;
  position: number;
  instructions: string;
  required_inputs: string[];
}

export interface AdminTemplateVersion {
  id: string;
  version: number;
  system_prompt: string;
  settings: Record<string, unknown>;
  sections: AdminTemplateSection[];
  created_at: string;
}

export interface AdminTemplate {
  id: string;
  key: string;
  name: string;
  description: string | null;
  status: "draft" | "published" | "archived";
  versions: AdminTemplateVersion[];
  created_at: string;
  updated_at: string;
}

export interface ModerationItem {
  content_type: "document" | "report";
  content_id: string;
  owner_id: string;
  owner_display_name: string;
  title: string;
  summary: string;
  hits: Array<Record<string, unknown>>;
  status: "pending" | "approved" | "restricted" | "removed";
  note: string | null;
  created_at: string;
}

export interface Announcement {
  id: string;
  title: string;
  content: string;
  pinned: boolean;
  published_at: string | null;
  expires_at: string | null;
  is_published: boolean;
  created_at: string;
  updated_at: string;
}
