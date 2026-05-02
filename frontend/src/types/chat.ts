export type Citation = {
  chunk_id: string;
  law_name?: string | null;
  article_no?: string | null;
  section?: string | null;
  source?: string | null;
  source_type?: string | null;
  case_id?: string | null;
  case_name?: string | null;
};

export type CitationDetail = Citation & {
  text: string;
  tags?: string | null;
  charges?: string | null;
  articles?: string | null;
  score?: number | null;
};

export type ReasoningSignature = {
  facts: string[];
  rules: string[];
  risks: string[];
  suggestions: string[];
};

export type ChatRole = "user" | "assistant" | "system";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  citations: Citation[];
  reasoning?: ReasoningSignature;
};

export type ChatApiResponse = {
  answer_json?: Record<string, unknown>;
  audio_url?: string | null;
  tts_job_id?: string | null;
};

export type ChatStreamEvent =
  | { type: "status"; phase: string }
  | { type: "delta"; text: string }
  | { type: "final"; answer_json?: Record<string, unknown>; audio_url?: string | null; tts_job_id?: string | null }
  | { type: "error"; detail?: string };
