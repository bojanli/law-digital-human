<template>
  <div class="chat-page">
    <Sidebar
      :sessions="sessions"
      :active-session-id="activeSessionId"
      :collapsed="sidebarCollapsed"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
      @new-session="createSession"
      @select-session="selectSession"
    />

    <div v-if="!sidebarCollapsed" class="sidebar-mask" @click="sidebarCollapsed = true" />

    <section class="chat-main">
      <ChatHeader
        title="高校法律普法数字人"
        :backend-online="backendOk"
        :is-recording="isRecording"
        :is-transcribing="isTranscribing"
        :is-speaking="avatarState.isPlaying"
        :avatar-connected="avatarState.ready"
        :avatar-collapsed="avatarCollapsed"
        :speech-controls-expanded="speechControlsExpanded"
        @toggle-avatar="avatarCollapsed = !avatarCollapsed"
        @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed"
        @toggle-speech-controls="speechControlsExpanded = !speechControlsExpanded"
      />

      <ChatWindow
        :messages="activeMessages"
        @select-suggestion="handleSuggestedQuestion"
        @select-citation="openCitationDetail"
      />

      <section v-show="speechControlsExpanded" class="speech-controls glass-panel depth-soft">
        <div class="speech-row">
          <label>语速 {{ speechRateScale.toFixed(2) }}</label>
          <input v-model.number="speechRateScale" type="range" min="0.8" max="1.25" step="0.01" />
          <label>音调 {{ speechPitchScale.toFixed(2) }}</label>
          <input v-model.number="speechPitchScale" type="range" min="0.8" max="1.25" step="0.01" />
          <label>音量 {{ speechVolumeScale.toFixed(2) }}</label>
          <input v-model.number="speechVolumeScale" type="range" min="0.7" max="1.2" step="0.01" />
        </div>
        <div class="speech-row actions">
          <button type="button" class="speech-btn" :disabled="!canRepeatCurrentSentence" @click="repeatCurrentSentence">
            重读本句
          </button>
          <button type="button" class="speech-btn" :disabled="!canResumeFromCurrentSentence" @click="resumeFromCurrentSentence">
            从当前句继续
          </button>
        </div>
      </section>

      <ChatInput
        v-model="draft"
        placeholder="输入你的法律问题，例如：房东不退押金，我该怎么维权？"
        :disabled="loading"
        :send-disabled="loading || !draft.trim() || isTranscribing"
        :voice-disabled="!supportsVoice || loading || isTranscribing"
        :voice-label="isRecording ? '结束语音' : '语音输入'"
        :listening-text="voiceStatusText"
        :interrupt-visible="true"
        :interrupt-disabled="!avatarState.isPlaying"
        :interrupt-label="'打断播报'"
        @submit="handleSubmit"
        @toggle-voice="toggleRecording"
        @clear="clearCurrentSession"
        @interrupt="interruptSpeechOutput"
      />
    </section>

    <AvatarPanel
      :avatar-status="avatarPanelStatus"
      :subtitle="avatarState.subtitle"
      :connected="avatarState.ready"
      :collapsed="avatarCollapsed"
    >
      <AvatarContainer />
    </AvatarPanel>

    <CitationDetailModal
      :visible="citationModalVisible"
      :citation="activeCitation"
      :detail="activeCitationDetail"
      :loading="citationDetailLoading"
      :error="citationDetailError"
      @close="closeCitationDetail"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import axios from "axios";
import AvatarContainer from "../components/AvatarContainer.vue";
import AvatarPanel from "../components/AvatarPanel.vue";
import ChatHeader from "../components/ChatHeader.vue";
import ChatInput from "../components/ChatInput.vue";
import ChatWindow from "../components/ChatWindow.vue";
import CitationDetailModal from "../components/CitationDetailModal.vue";
import Sidebar from "../components/Sidebar.vue";
import {
  type AvatarEmotion,
  avatarState,
  playAvatar,
  setAvatarPose,
  setAvatarAudioOptions,
  setAvatarSubtitle,
  normalizeAvatarEmotion,
  stopAvatar,
} from "../services/avatarBridge";
import { buildChatSettingsPayload, isUnityAvatarEnabled, loadLocalSettings } from "../services/appSettings";
import { ElMessage } from "element-plus";
import type { ChatApiResponse, ChatMessage, ChatStreamEvent, Citation, CitationDetail, ReasoningSignature } from "../types/chat";

type SessionRecord = {
  id: string;
  title: string;
  updatedAt: string;
  messages: ChatMessage[];
};

const quickPrompts = [
  "房东不退押金怎么办？",
  "兼职被拖欠工资如何维权？",
  "网购到假货如何取证？",
];

const supportsVoice = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
const draft = ref("");
const loading = ref(false);
const backendOk = ref(true);
const sidebarCollapsed = ref(typeof window !== "undefined" ? window.innerWidth <= 900 : false);
const avatarCollapsed = ref(false);
const isRecording = ref(false);
const isTranscribing = ref(false);
const activeSessionId = ref(createSessionId());
let mediaStream: MediaStream | null = null;
let audioContext: AudioContext | null = null;
let mediaSourceNode: MediaStreamAudioSourceNode | null = null;
let processorNode: ScriptProcessorNode | null = null;
let muteNode: GainNode | null = null;
let pcmChunks: Float32Array[] = [];
let inputSampleRate = 48000;
let idleResetTimer: number | null = null;
let speechRunId = 0;
const speechControlsExpanded = ref(false);
const speechRateScale = ref(1);
const speechPitchScale = ref(1);
const speechVolumeScale = ref(1);
const speechMaxSentenceLen = ref(32);
const lastSpeechText = ref("");
const lastSpeechEmotion = ref<AvatarEmotion>("calm");
const lastSpeechGesture = ref("explain");
const speechSentences = ref<string[]>([]);
const currentSentenceIndex = ref(-1);
const pausedSentenceIndex = ref(-1);
const canResumeFromCurrentSentence = computed(() => pausedSentenceIndex.value >= 0 && speechSentences.value.length > 0);
const canRepeatCurrentSentence = computed(() => currentSentenceIndex.value >= 0 && speechSentences.value.length > 0);
const citationModalVisible = ref(false);
const activeCitation = ref<Citation | null>(null);
const activeCitationDetail = ref<CitationDetail | null>(null);
const citationDetailLoading = ref(false);
const citationDetailError = ref("");
const citationDetailCache = ref<Record<string, CitationDetail>>({});

const WARNING_KEYWORDS = ["风险", "违法", "证据", "不足", "谨慎", "败诉", "报警", "起诉", "仲裁", "投诉", "处罚", "侵权", "责任"];

const sessions = ref<SessionRecord[]>([
  {
    id: activeSessionId.value,
    title: "新对话",
    updatedAt: formatSessionTime(),
    messages: [buildWelcomeMessage()],
  },
]);

const activeSession = computed(() => sessions.value.find((session) => session.id === activeSessionId.value) || sessions.value[0]);
const activeMessages = computed(() => activeSession.value?.messages || []);
const voiceStatusText = computed(() => {
  if (isRecording.value) return "正在聆听...";
  if (isTranscribing.value) return "语音转写中...";
  if (avatarState.isPlaying) return "数字人正在播报...";
  return "";
});
const avatarPanelStatus = computed<"idle" | "listening" | "thinking" | "speaking" | "disconnected">(() => {
  if (!avatarState.ready) return "disconnected";
  if (avatarState.isPlaying) return "speaking";
  if (isRecording.value) return "listening";
  if (loading.value || isTranscribing.value) return "thinking";
  return "idle";
});

function buildWelcomeMessage(): ChatMessage {
  return {
    id: "boot",
    role: "assistant",
    text: "你好，我是高校法律普法数字人。你描述事实，我会结合可核验依据给出分析和建议。",
    citations: [],
    reasoning: {
      facts: ["等待用户输入事实。"],
      rules: ["收到问题后检索法条与案例依据。"],
      risks: ["事实不完整时，只输出谨慎结论。"],
      suggestions: quickPrompts,
    },
  };
}

function createSessionId(): string {
  return `web_${Date.now().toString(36)}_${Math.random().toString(16).slice(2, 6)}`;
}

function formatSessionTime(date = new Date()): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function nextId(): string {
  return `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

function updateCurrentSession(updater: (session: SessionRecord) => void): void {
  const session = activeSession.value;
  if (!session) return;
  updater(session);
  session.updatedAt = formatSessionTime();
  if (session.messages.length > 1) {
    const firstUser = session.messages.find((message) => message.role === "user");
    if (firstUser?.text.trim()) {
      session.title = firstUser.text.trim().slice(0, 14);
    }
  }
}

function createSession(): void {
  activeSessionId.value = createSessionId();
  sessions.value.unshift({
    id: activeSessionId.value,
    title: "新对话",
    updatedAt: formatSessionTime(),
    messages: [buildWelcomeMessage()],
  });
  draft.value = "";
  if (unityAvatarEnabled()) {
    stopAvatar();
  }
  setAvatarSubtitle("");
  clearIdleResetTimer();
  if (typeof window !== "undefined" && window.innerWidth <= 900) {
    sidebarCollapsed.value = true;
  }
}

function selectSession(sessionId: string): void {
  activeSessionId.value = sessionId;
  if (typeof window !== "undefined" && window.innerWidth <= 900) {
    sidebarCollapsed.value = true;
  }
}

async function openCitationDetail(citation: Citation): Promise<void> {
  activeCitation.value = citation;
  activeCitationDetail.value = null;
  citationDetailError.value = "";
  citationModalVisible.value = true;

  const cached = citationDetailCache.value[citation.chunk_id];
  if (cached) {
    activeCitationDetail.value = cached;
    return;
  }

  citationDetailLoading.value = true;
  try {
    const res = await axios.get<CitationDetail>(`/api/knowledge/chunk/${encodeURIComponent(citation.chunk_id)}`);
    citationDetailCache.value[citation.chunk_id] = res.data;
    activeCitationDetail.value = res.data;
  } catch {
    citationDetailError.value = "依据内容加载失败，请稍后重试。";
  } finally {
    citationDetailLoading.value = false;
  }
}

function closeCitationDetail(): void {
  citationModalVisible.value = false;
}

function clearCurrentSession(): void {
  updateCurrentSession((session) => {
    session.messages = [buildWelcomeMessage()];
  });
  draft.value = "";
  interruptSpeechOutput();
  if (unityAvatarEnabled()) {
    stopAvatar();
  }
  clearIdleResetTimer();
}

function clearIdleResetTimer(): void {
  if (idleResetTimer !== null && typeof window !== "undefined") {
    window.clearTimeout(idleResetTimer);
    idleResetTimer = null;
  }
}

function scheduleAvatarIdleReset(delayMs = 1500): void {
  if (typeof window === "undefined") {
    return;
  }
  clearIdleResetTimer();
  idleResetTimer = window.setTimeout(() => {
    setAvatarPose("idle", "calm");
    idleResetTimer = null;
  }, delayMs);
}

function unityAvatarEnabled(): boolean {
  return isUnityAvatarEnabled(loadLocalSettings());
}

function isWarningReply(text: string): boolean {
  return WARNING_KEYWORDS.some((keyword) => text.includes(keyword));
}

function resolveAvatarReplyPose(text: string): { gesture: string; emotion: AvatarEmotion } {
  if (isWarningReply(text)) {
    return { gesture: "point", emotion: "warning" };
  }
  return { gesture: "explain", emotion: "supportive" };
}

function appendAssistantSystemMessage(text: string, suggestions: string[]): void {
  updateCurrentSession((session) => {
    session.messages.push({
      id: nextId(),
      role: "assistant",
      text,
      citations: [],
      reasoning: {
        facts: ["会话状态已更新。"],
        rules: ["未调用后端检索。"],
        risks: ["请继续补充可核验信息。"],
        suggestions,
      },
    });
  });
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function toCitationList(value: unknown): Citation[] {
  if (!Array.isArray(value)) return [];
  const output: Citation[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const raw = item as Record<string, unknown>;
    const chunkId = typeof raw.chunk_id === "string" ? raw.chunk_id.trim() : "";
    if (!chunkId) continue;
    output.push({
      chunk_id: chunkId,
      law_name: typeof raw.law_name === "string" ? raw.law_name : null,
      article_no: typeof raw.article_no === "string" ? raw.article_no : null,
      section: typeof raw.section === "string" ? raw.section : null,
      source: typeof raw.source === "string" ? raw.source : null,
      source_type: typeof raw.source_type === "string" ? raw.source_type : null,
      case_id: typeof raw.case_id === "string" ? raw.case_id : null,
      case_name: typeof raw.case_name === "string" ? raw.case_name : null,
    });
  }
  return output;
}

function buildReasoning(answerJson: Record<string, unknown>, citations: Citation[]): ReasoningSignature {
  const facts = toStringList(answerJson.assumptions);
  const analysis = toStringList(answerJson.analysis);
  const followUps = toStringList(answerJson.follow_up_questions);
  const actions = toStringList(answerJson.actions);
  const rules = citations.map((citation) => {
    if (citation.source_type === "case") {
      return `${citation.case_name || "真实案例"} ${citation.case_id ? `#${citation.case_id}` : ""}`.trim();
    }
    return `${citation.law_name || "法律条文"} ${citation.article_no || ""}`.trim();
  });

  return {
    facts: (facts.length ? facts : analysis).slice(0, 3),
    rules: (rules.length ? rules : ["当前轮未命中可核验法条，建议补充证据。"]).slice(0, 3),
    risks: (followUps.length ? followUps.map((item) => `待确认：${item}`) : ["请核对时间线与证据来源，避免事实偏差。"]).slice(0, 3),
    suggestions: (followUps.length ? followUps : actions.length ? actions : quickPrompts).slice(0, 4),
  };
}

function composeAssistantText(answerJson: Record<string, unknown>, citations: Citation[]): string {
  const rawConclusion = answerJson.conclusion;
  const conclusion = typeof rawConclusion === "string" && rawConclusion.trim()
    ? rawConclusion.replace(/\s*\[\[CITATIONS:[^\]]*\]\]\s*/gi, " ").trim()
    : "当前暂无法输出稳定结论，请补充事实后继续。";
  const actions = toStringList(answerJson.actions).slice(0, 2);
  const lines = [conclusion];
  if (actions.length) lines.push(`建议：${actions.join("；")}`);
  if (citations.length) lines.push(`本轮已引用 ${citations.length} 条依据。`);
  return lines.join("\n");
}

function stopLocalSpeech(): void {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return;
  }
  try {
    window.speechSynthesis.cancel();
  } catch {
    // no-op
  }
  avatarState.isPlaying = false;
  if (currentSentenceIndex.value >= 0 && speechSentences.value.length > 0) {
    pausedSentenceIndex.value = Math.min(currentSentenceIndex.value, speechSentences.value.length - 1);
  }
}

function resolveLocalSpeechProsody(emotion: AvatarEmotion): { rate: number; pitch: number; volume: number } {
  if (emotion === "warning") return { rate: 0.98, pitch: 1.1, volume: 1.0 };
  if (emotion === "supportive") return { rate: 1.02, pitch: 1.08, volume: 1.0 };
  if (emotion === "serious") return { rate: 0.93, pitch: 0.9, volume: 1.0 };
  return { rate: 1.0, pitch: 1.0, volume: 1.0 };
}

type LegalSpeechStyle = "judge" | "explain" | "warn" | "reassure";

function resolveLegalSpeechStyle(text: string, emotion: AvatarEmotion): LegalSpeechStyle {
  if (emotion === "warning" || /风险|违法|处罚|败诉|警惕|后果/.test(text)) return "warn";
  if (emotion === "serious" || /裁定|判决|应当|依据|本院认为|结论/.test(text)) return "judge";
  if (emotion === "supportive" || /建议|可以|先|步骤|帮助|维权/.test(text)) return "reassure";
  return "explain";
}

function resolveStyleProsody(style: LegalSpeechStyle): { rate: number; pitch: number; volume: number; pauseFactor: number } {
  if (style === "judge") return { rate: 0.92, pitch: 0.9, volume: 1.03, pauseFactor: 1.2 };
  if (style === "warn") return { rate: 0.97, pitch: 1.06, volume: 1.05, pauseFactor: 1.12 };
  if (style === "reassure") return { rate: 1.0, pitch: 1.1, volume: 1.0, pauseFactor: 1.0 };
  return { rate: 1.02, pitch: 1.0, volume: 1.0, pauseFactor: 1.0 };
}

function mergeProsody(
  emotion: AvatarEmotion,
  style: LegalSpeechStyle,
): { rate: number; pitch: number; volume: number; pauseFactor: number } {
  const e = resolveLocalSpeechProsody(emotion);
  const s = resolveStyleProsody(style);
  return {
    rate: Math.min(1.3, Math.max(0.75, e.rate * s.rate * speechRateScale.value)),
    pitch: Math.min(1.35, Math.max(0.75, e.pitch * s.pitch * speechPitchScale.value)),
    volume: Math.min(1.0, Math.max(0.2, e.volume * s.volume * speechVolumeScale.value)),
    pauseFactor: s.pauseFactor,
  };
}

function pickPreferredChineseVoice(): SpeechSynthesisVoice | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return null;
  }
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  const zhVoices = voices.filter((v) => /^zh/i.test(v.lang) || /chinese|中文|普通话/i.test(v.name));
  if (!zhVoices.length) return null;
  const preferred = zhVoices.find((v) => /neural|xiaoxiao|yunxi|晓晓|云希|natural/i.test(v.name));
  return preferred || zhVoices[0] || null;
}

function splitLongSentence(sentence: string, maxLen: number): string[] {
  const input = sentence.trim();
  if (!input) return [];
  if (input.length <= maxLen) return [input];
  const pieces: string[] = [];
  let cursor = 0;
  while (cursor < input.length) {
    let end = Math.min(cursor + maxLen, input.length);
    if (end < input.length) {
      const windowText = input.slice(cursor, end);
      const splitPos = Math.max(
        windowText.lastIndexOf("，"),
        windowText.lastIndexOf("；"),
        windowText.lastIndexOf("："),
        windowText.lastIndexOf(","),
        windowText.lastIndexOf(";"),
        windowText.lastIndexOf(":"),
        windowText.lastIndexOf(" "),
      );
      if (splitPos >= 12) {
        end = cursor + splitPos + 1;
      }
    }
    pieces.push(input.slice(cursor, end).trim());
    cursor = end;
  }
  return pieces.filter(Boolean);
}

function splitForSpeech(text: string, maxLen: number): string[] {
  const normalized = text
    .replace(/\s*\n+\s*/g, "。")
    .replace(/\s{2,}/g, " ")
    .trim();
  if (!normalized) return [];
  const rough = normalized
    .split(/(?<=[。！？；!?;:：])/g)
    .map((x) => x.trim())
    .filter(Boolean);
  const refined = (rough.length ? rough : [normalized]).flatMap((item) => splitLongSentence(item, maxLen));
  return refined;
}

function isEnumeratedSentence(sentence: string): boolean {
  return /(第[一二三四五六七八九十百\d]+|首先|其次|再次|最后|其一|其二|其三|第一|第二|第三)/.test(sentence);
}

function speechPauseMs(sentence: string, pauseFactor: number): number {
  let base = 90;
  if (/[。！？!?]$/.test(sentence)) base = 220;
  else if (/[；;]$/.test(sentence)) base = 170;
  else if (/[，,：:]$/.test(sentence)) base = 120;
  if (isEnumeratedSentence(sentence)) base += 140;
  return Math.round(base * pauseFactor);
}

async function speakWithLocalTtsSegmented(
  text: string,
  emotion: AvatarEmotion,
  gesture: string,
  runId: number,
  startIndex = 0,
): Promise<void> {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return;
  }
  const style = resolveLegalSpeechStyle(text, emotion);
  const sentences = splitForSpeech(text, speechMaxSentenceLen.value);
  if (!sentences.length) {
    return;
  }
  speechSentences.value = sentences;
  lastSpeechText.value = text;
  lastSpeechEmotion.value = emotion;
  lastSpeechGesture.value = gesture;
  pausedSentenceIndex.value = -1;
  stopLocalSpeech();
  const prosody = mergeProsody(emotion, style);
  const preferredVoice = pickPreferredChineseVoice();
  avatarState.isPlaying = true;
  if (unityAvatarEnabled()) {
    setAvatarPose(gesture, emotion, text);
  }
  for (let i = startIndex; i < sentences.length; i += 1) {
    const sentence = sentences[i];
    if (!sentence) continue;
    if (runId !== speechRunId) return;
    currentSentenceIndex.value = i;
    await new Promise<void>((resolve) => {
      try {
        const utterance = new SpeechSynthesisUtterance(sentence);
        utterance.lang = preferredVoice?.lang || "zh-CN";
        if (preferredVoice) utterance.voice = preferredVoice;
        utterance.rate = prosody.rate;
        utterance.pitch = prosody.pitch;
        utterance.volume = prosody.volume;
        utterance.onstart = () => {
          if (runId !== speechRunId) return;
          setAvatarSubtitle(sentence);
        };
        utterance.onend = () => resolve();
        utterance.onerror = () => resolve();
        window.speechSynthesis.speak(utterance);
      } catch {
        resolve();
      }
    });
    if (runId !== speechRunId) return;
    await new Promise((resolve) => window.setTimeout(resolve, speechPauseMs(sentence, prosody.pauseFactor)));
  }
  if (runId !== speechRunId) return;
  currentSentenceIndex.value = -1;
  pausedSentenceIndex.value = -1;
  avatarState.isPlaying = false;
  scheduleAvatarIdleReset(260);
}

function interruptSpeechOutput(): void {
  speechRunId += 1;
  stopLocalSpeech();
  if (unityAvatarEnabled()) {
    stopAvatar();
  }
  clearIdleResetTimer();
  if (unityAvatarEnabled()) {
    setAvatarPose("idle", "calm");
  }
}

function repeatCurrentSentence(): void {
  if (currentSentenceIndex.value < 0 || !speechSentences.value.length) return;
  const idx = Math.min(currentSentenceIndex.value, speechSentences.value.length - 1);
  const runId = ++speechRunId;
  void speakWithLocalTtsSegmented(lastSpeechText.value, lastSpeechEmotion.value, lastSpeechGesture.value, runId, idx);
}

function resumeFromCurrentSentence(): void {
  if (pausedSentenceIndex.value < 0 || !speechSentences.value.length) return;
  const idx = Math.min(pausedSentenceIndex.value, speechSentences.value.length - 1);
  const runId = ++speechRunId;
  void speakWithLocalTtsSegmented(lastSpeechText.value, lastSpeechEmotion.value, lastSpeechGesture.value, runId, idx);
}

async function sendMessage(overrideInput?: string): Promise<void> {
  if (avatarState.isPlaying) {
    interruptSpeechOutput();
  }
  const rawInput = typeof overrideInput === "string" ? overrideInput : draft.value;
  const input = rawInput.trim();
  if (!input || loading.value) return;

  updateCurrentSession((session) => {
    session.messages.push({ id: nextId(), role: "user", text: input, citations: [] });
    session.messages.push({ id: nextId(), role: "assistant", text: "正在检索依据...", citations: [] });
  });
  const assistantMessageId = activeSession.value?.messages[activeSession.value.messages.length - 1]?.id || "";
  draft.value = "";
  loading.value = true;
  clearIdleResetTimer();
  if (unityAvatarEnabled()) {
    setAvatarPose("Thoughtful Head Shake", "serious", input);
  }

  try {
    const streamed = await sendMessageStream(input, assistantMessageId);
    if (!streamed) {
      const res = await axios.post<ChatApiResponse>("/api/chat", {
        session_id: activeSessionId.value,
        text: input,
        mode: "chat",
        case_state: null,
        ...buildChatSettingsPayload(),
      });
      console.log("[Chat] raw response =", res);
      await applyFinalAnswer(
        assistantMessageId,
        (res.data?.answer_json || {}) as Record<string, unknown>,
        typeof res.data?.audio_url === "string" ? res.data.audio_url : null,
      );
    }
    backendOk.value = true;
  } catch {
    backendOk.value = false;
    if (unityAvatarEnabled()) {
      setAvatarPose("Thoughtful Head Shake", "serious");
    }
    replaceAssistantMessage(assistantMessageId, {
      id: assistantMessageId,
      role: "assistant",
      text: "后端暂时不可用。我先记录你的问题，稍后重试即可继续。",
      citations: [],
      reasoning: {
        facts: ["用户已提交问题，等待服务恢复。"],
        rules: ["当前未能获取检索结果。"],
        risks: ["无法生成可核验引用，暂停结论输出。"],
        suggestions: quickPrompts,
      },
    });
  } finally {
    loading.value = false;
  }
}

function replaceAssistantMessage(messageId: string, nextMessage: ChatMessage): void {
  updateCurrentSession((session) => {
    const index = session.messages.findIndex((message) => message.id === messageId);
    if (index >= 0) {
      session.messages[index] = nextMessage;
    } else {
      session.messages.push(nextMessage);
    }
  });
}

function updateAssistantDraft(messageId: string, text: string): void {
  replaceAssistantMessage(messageId, {
    id: messageId,
    role: "assistant",
    text: text || "正在生成答复...",
    citations: [],
  });
}

async function applyFinalAnswer(
  messageId: string,
  answerJson: Record<string, unknown>,
  audioUrl: string | null = null,
): Promise<void> {
  speechRunId += 1;
  const citations = toCitationList(answerJson.citations);
  const reasoning = buildReasoning(answerJson, citations);
  const assistantText = composeAssistantText(answerJson, citations);
  const modelEmotion = normalizeAvatarEmotion(answerJson.emotion);
  const resolvedPose = resolveAvatarReplyPose(assistantText);
  const emotion = resolvedPose.emotion || modelEmotion;
  const gesture = resolvedPose.gesture;
  replaceAssistantMessage(messageId, {
    id: messageId,
    role: "assistant",
    text: assistantText,
    citations,
    reasoning,
  });

  const useUnityAvatar = unityAvatarEnabled();
  if (useUnityAvatar) {
    setAvatarPose(gesture, emotion, assistantText);
    setAvatarSubtitle(assistantText);
  }
  if (audioUrl && audioUrl.trim()) {
    const speed = Math.min(1.35, Math.max(0.75, speechRateScale.value));
    const volume = Math.min(1, Math.max(0.2, speechVolumeScale.value));
    setAvatarAudioOptions({ rate: speed, volume });
    if (Math.abs(speechPitchScale.value - 1) > 0.01) {
      ElMessage.info("当前为后端真人音色，音调参数仅在本地语音兜底时生效。");
    }
    if (useUnityAvatar) {
      playAvatar(audioUrl, assistantText, emotion, gesture);
      return;
    }
  }
  avatarState.isPlaying = false;
  currentSentenceIndex.value = -1;
  pausedSentenceIndex.value = -1;
}

async function sendMessageStream(input: string, assistantMessageId: string): Promise<boolean> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: activeSessionId.value,
      text: input,
      mode: "chat",
      case_state: null,
      ...buildChatSettingsPayload(),
    }),
  });
  if (!response.ok || !response.body) {
    return false;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamedText = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      const event = JSON.parse(trimmed) as ChatStreamEvent;
      if (event.type === "status") {
        const label = event.phase === "search" ? "正在检索依据..." : event.phase === "answer" ? "正在生成答复..." : "正在整理上下文...";
        updateAssistantDraft(assistantMessageId, streamedText || label);
        continue;
      }
      if (event.type === "delta") {
        streamedText += event.text;
        updateAssistantDraft(assistantMessageId, streamedText);
        continue;
      }
      if (event.type === "final") {
        console.log("[Chat] raw stream final =", event);
        await applyFinalAnswer(
          assistantMessageId,
          (event.answer_json || {}) as Record<string, unknown>,
          typeof event.audio_url === "string" ? event.audio_url : null,
        );
        return true;
      }
      if (event.type === "error") {
        throw new Error(event.detail || "stream failed");
      }
    }
  }
  return false;
}

function handleSubmit(): void {
  void sendMessage();
}

function handleSuggestedQuestion(question: string): void {
  draft.value = question;
  void sendMessage(question);
}

async function toggleRecording(): Promise<void> {
  if (isRecording.value) {
    isRecording.value = false;
    appendAssistantSystemMessage("已停止录音，正在上传转写...", []);
    await stopPcmCapture();
    return;
  }

  if (!supportsVoice || loading.value || isTranscribing.value) return;

  try {
    await startPcmCapture();
    isRecording.value = true;
    appendAssistantSystemMessage("开始录音，请直接描述情况，再次点击可结束。", []);
  } catch {
    isRecording.value = false;
    appendAssistantSystemMessage("麦克风启动失败，请检查浏览器权限后重试。", []);
  }
}

async function transcribeAndSend(): Promise<void> {
  if (!pcmChunks.length) return;
  isTranscribing.value = true;
  try {
    const wavBuffer = exportWavFromPcm(pcmChunks, inputSampleRate, 16000);
    const audioBlob = new Blob([wavBuffer], { type: "audio/wav" });
    const audioBase64 = await blobToBase64(audioBlob);
    const resp = await axios.post<{ text?: string; detail?: string; log_id?: string }>("/api/asr/transcribe", {
      audio_base64: audioBase64,
      mime_type: "audio/wav",
    });
    const text = (resp.data?.text || "").trim();
    if (!text) {
      appendAssistantSystemMessage(
        `语音未识别出文本。${resp.data?.detail ? `原因：${resp.data.detail}` : "请提高音量并靠近麦克风重试。"}${resp.data?.log_id ? `（log_id: ${resp.data.log_id}）` : ""}`,
        [],
      );
      return;
    }
    draft.value = text;
    await sendMessage(text);
  } catch {
    appendAssistantSystemMessage("语音转写失败，请改用文本继续提问。", []);
  } finally {
    isTranscribing.value = false;
    pcmChunks = [];
  }
}

async function startPcmCapture(): Promise<void> {
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
      sampleRate: 16000,
      sampleSize: 16,
    },
  });
  audioContext = new AudioContext();
  inputSampleRate = audioContext.sampleRate;
  pcmChunks = [];

  mediaSourceNode = audioContext.createMediaStreamSource(mediaStream);
  processorNode = audioContext.createScriptProcessor(2048, 1, 1);
  muteNode = audioContext.createGain();
  muteNode.gain.value = 0;
  processorNode.onaudioprocess = (event: AudioProcessingEvent) => {
    pcmChunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
  };

  mediaSourceNode.connect(processorNode);
  processorNode.connect(muteNode);
  muteNode.connect(audioContext.destination);
}

async function stopPcmCapture(): Promise<void> {
  processorNode?.disconnect();
  mediaSourceNode?.disconnect();
  muteNode?.disconnect();
  processorNode = null;
  mediaSourceNode = null;
  muteNode = null;
  mediaStream?.getTracks().forEach((track) => track.stop());
  mediaStream = null;
  if (audioContext) {
    await audioContext.close();
    audioContext = null;
  }
  await transcribeAndSend();
}

function exportWavFromPcm(chunks: Float32Array[], srcRate: number, targetRate: number): ArrayBuffer {
  const merged = mergeFloat32(chunks);
  const downsampled = srcRate === targetRate ? merged : downsampleBuffer(merged, srcRate, targetRate);
  const pcm16 = floatTo16BitPCM(downsampled);
  return encodeWav(pcm16, targetRate);
}

function mergeFloat32(chunks: Float32Array[]): Float32Array {
  const total = chunks.reduce((sum, arr) => sum + arr.length, 0);
  const out = new Float32Array(total);
  let offset = 0;
  for (const arr of chunks) {
    out.set(arr, offset);
    offset += arr.length;
  }
  return out;
}

function downsampleBuffer(buffer: Float32Array, srcRate: number, targetRate: number): Float32Array {
  const ratio = srcRate / targetRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;
  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i += 1) {
      accum += buffer[i] || 0;
      count += 1;
    }
    result[offsetResult] = count > 0 ? accum / count : 0;
    offsetResult += 1;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

function floatTo16BitPCM(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    const s = Math.max(-1, Math.min(1, input[i] || 0));
    out[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff);
  }
  return out;
}

function encodeWav(samples: Int16Array, sampleRate: number): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i += 1, offset += 2) {
    view.setInt16(offset, samples[i] || 0, true);
  }
  return buffer;
}

function writeAscii(view: DataView, offset: number, text: string): void {
  for (let i = 0; i < text.length; i += 1) {
    view.setUint8(offset + i, text.charCodeAt(i));
  }
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      const idx = result.indexOf(",");
      if (idx < 0) {
        reject(new Error("invalid data url"));
        return;
      }
      resolve(result.slice(idx + 1));
    };
    reader.onerror = () => reject(reader.error || new Error("read blob failed"));
    reader.readAsDataURL(blob);
  });
}

onBeforeUnmount(() => {
  interruptSpeechOutput();
  clearIdleResetTimer();
  if (isRecording.value) {
    void stopPcmCapture();
  }
  mediaStream?.getTracks().forEach((track) => track.stop());
});
</script>

<style scoped>
.chat-page {
  height: 100%;
  display: flex;
  gap: 1rem;
  overflow: hidden;
}

.chat-main {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 1rem;
  height: 100%;
}

.sidebar-mask {
  display: none;
}

.speech-controls {
  border-radius: 20px;
  padding: 0.75rem 0.9rem;
  display: grid;
  gap: 0.55rem;
}

.speech-row {
  display: grid;
  grid-template-columns: auto 1fr auto 1fr auto 1fr;
  gap: 0.45rem;
  align-items: center;
  font-size: 0.82rem;
}

.speech-row.actions {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.speech-btn {
  border: 1px solid rgba(88, 120, 176, 0.18);
  border-radius: 12px;
  padding: 0.5rem 0.75rem;
  background: rgba(255, 255, 255, 0.82);
  color: var(--text-primary);
  cursor: pointer;
}

.speech-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

@media (max-width: 900px) {
  .chat-page {
    position: relative;
    flex-direction: column;
  }

  .chat-main {
    min-height: 0;
  }

  .sidebar-mask {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(8, 18, 34, 0.24);
    z-index: 40;
  }

  .speech-row {
    grid-template-columns: 1fr;
  }

  .speech-row.actions {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
