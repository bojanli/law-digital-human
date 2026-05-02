export type AppSettings = {
  chat_top_k: number;
  hybrid_retrieval: boolean;
  enable_rerank: boolean;
  reject_without_evidence: boolean;
  strict_citation_check: boolean;
  enable_tts: boolean;
  enable_unity_avatar: boolean;
  default_emotion: "calm" | "supportive" | "serious" | "warning";
  knowledge_collection: string;
  case_collection: string;
  chat_case_top_k: number;
  embedding_provider: "mock" | "ark" | "doubao";
  timeout_sec: number;
  llm_provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
};

const STORAGE_KEY = "law_digital_human_settings_v1";

export const DEFAULT_APP_SETTINGS: AppSettings = {
  chat_top_k: 5,
  hybrid_retrieval: false,
  enable_rerank: true,
  reject_without_evidence: false,
  strict_citation_check: true,
  enable_tts: true,
  enable_unity_avatar: true,
  default_emotion: "calm",
  knowledge_collection: "laws",
  case_collection: "cases",
  chat_case_top_k: 3,
  embedding_provider: "mock",
  timeout_sec: 30,
  llm_provider: "mock",
  model_name: "",
  temperature: 0.2,
  max_tokens: 260,
};

function clampNumber(value: unknown, fallback: number, min: number, max: number): number {
  const numeric = typeof value === "number" && Number.isFinite(value) ? value : fallback;
  return Math.min(max, Math.max(min, numeric));
}

export function normalizeSettings(value: Partial<AppSettings> | null | undefined): AppSettings {
  const raw = value || {};
  return {
    ...DEFAULT_APP_SETTINGS,
    ...raw,
    chat_top_k: Math.round(clampNumber(raw.chat_top_k, DEFAULT_APP_SETTINGS.chat_top_k, 1, 12)),
    chat_case_top_k: Math.round(clampNumber(raw.chat_case_top_k, DEFAULT_APP_SETTINGS.chat_case_top_k, 0, 12)),
    timeout_sec: Math.round(clampNumber(raw.timeout_sec, DEFAULT_APP_SETTINGS.timeout_sec, 5, 90)),
    temperature: clampNumber(raw.temperature, DEFAULT_APP_SETTINGS.temperature, 0, 1),
    max_tokens: Math.round(clampNumber(raw.max_tokens, DEFAULT_APP_SETTINGS.max_tokens, 128, 4096)),
    hybrid_retrieval: false,
  };
}

export function loadLocalSettings(): AppSettings {
  if (typeof window === "undefined") return DEFAULT_APP_SETTINGS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? normalizeSettings(JSON.parse(raw) as Partial<AppSettings>) : DEFAULT_APP_SETTINGS;
  } catch {
    return DEFAULT_APP_SETTINGS;
  }
}

export function saveLocalSettings(settings: AppSettings): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalizeSettings(settings)));
}

export function resetLocalSettings(): AppSettings {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(STORAGE_KEY);
  }
  return DEFAULT_APP_SETTINGS;
}

export function buildChatSettingsPayload(settings = loadLocalSettings()): Record<string, unknown> {
  return {
    top_k: settings.chat_top_k,
    use_hybrid_search: false,
    use_rerank: settings.enable_rerank,
    temperature: settings.temperature,
    max_tokens: settings.max_tokens,
    citation_strict: settings.strict_citation_check,
    enable_tts: settings.enable_tts,
  };
}

export function buildCaseSettingsPayload(settings = loadLocalSettings()): Record<string, unknown> {
  return {
    enable_tts: settings.enable_tts,
    citation_strict: settings.strict_citation_check,
  };
}

export function isUnityAvatarEnabled(settings = loadLocalSettings()): boolean {
  return settings.enable_unity_avatar;
}
