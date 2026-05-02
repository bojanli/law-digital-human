<template>
  <div class="case-page">
    <section class="left-column">
      <section class="top-nav-row">
        <RouterLink to="/" class="home-back-btn">返回主界面</RouterLink>
      </section>

      <aside class="case-sidebar glass-panel depth-medium" :class="{ collapsed: sidebarCollapsed }">
        <div class="sidebar-head">
          <div>
            <p class="eyebrow">Mock Court</p>
            <h2>案件模拟</h2>
          </div>
          <button type="button" class="toggle-btn mobile-only" @click="sidebarCollapsed = !sidebarCollapsed">
            {{ sidebarCollapsed ? "展开" : "收起" }}
          </button>
        </div>

        <div class="catalog-list">
          <p v-if="catalogLoading" class="empty-text">正在加载案件库...</p>
          <button
            v-for="item in catalog"
            :key="item.case_id"
            type="button"
            class="catalog-item"
            :class="{ active: selectedCaseId === item.case_id }"
            @click="selectedCaseId = item.case_id"
          >
            <span class="meta-row">
              <small>{{ item.category }}</small>
              <small>{{ item.difficulty }}</small>
            </span>
            <strong>{{ item.title }}</strong>
            <span>{{ item.summary }}</span>
          </button>
        </div>

        <div class="sidebar-actions">
          <button type="button" class="new-case-btn" :disabled="catalogLoading" @click="resetCase">
            返回案件选择
          </button>
          <button type="button" class="start-btn" :disabled="!selectedCaseId || starting" @click="startCase">
            {{ starting ? "正在组建法庭..." : sessionId ? "重新开庭" : "开庭审理" }}
          </button>
        </div>
      </aside>
    </section>

    <div v-if="!sidebarCollapsed" class="sidebar-mask" @click="sidebarCollapsed = true" />

    <section class="case-main">
      <ChatHeader
        :title="sessionId ? currentCaseTitle : '模拟法庭数字人'"
        :backend-online="backendOk"
        :is-recording="false"
        :is-transcribing="stepping || starting"
        :is-speaking="avatarState.isPlaying"
        :avatar-connected="avatarState.ready"
        :avatar-collapsed="avatarCollapsed"
        :speech-controls-expanded="false"
        @toggle-avatar="avatarCollapsed = !avatarCollapsed"
        @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed"
        @toggle-speech-controls="noop"
      />

      <section v-if="!sessionId" class="intro-panel glass-panel depth-soft">
        <p class="eyebrow">Courtroom Brief</p>
        <h1>选择案件后进入沉浸式庭审对话</h1>
        <p>
          你将以法官身份推进审理。左侧选择案件，中间阅读庭审过程并作出裁量，右侧数字人会同步播报法庭进程。
        </p>
      </section>

      <ChatWindow :messages="chatMessages">
        <template #extra-content>
          <section v-if="sessionId && currentOptions.length" class="options-panel glass-panel depth-soft">
            <p class="options-title">您作为法官，接下来可以采取以下行动，您选择？</p>
            <div class="options-grid">
              <button
                v-for="opt in currentOptions"
                :key="opt"
                type="button"
                class="option-btn"
                :disabled="stepping"
                @click="makeChoice(opt)"
              >
                {{ opt }}
              </button>
            </div>
          </section>
        </template>
      </ChatWindow>

      <ChatInput
        v-model="freeInput"
        :placeholder="sessionId ? '输入你的审判指令或裁量意见...' : '先在左侧选择案件并开庭，或提前输入你想采用的审理思路...'"
        :disabled="stepping"
        :send-disabled="stepping || !freeInput.trim()"
        :voice-disabled="true"
        voice-label="语音暂未接入"
        :listening-text="avatarState.isPlaying ? '数字人正在播报...' : ''"
        :interrupt-visible="true"
        :interrupt-disabled="!avatarState.isPlaying"
        interrupt-label="打断播报"
        @submit="sendFreeInput"
        @toggle-voice="noop"
        @clear="clearDraft"
        @interrupt="interruptCaseSpeech"
      >
        <template #toolbar-left>
          <StatusBadge :label="`第 ${turnCount} 轮`" tone="info" />
          <StatusBadge :label="phaseLabel" :tone="phaseTone" />
          <StatusBadge :label="currentQuestion ? '等待裁量' : '庭审推进中'" :tone="currentQuestion ? 'warning' : 'neutral'" />
        </template>
      </ChatInput>
    </section>

    <AvatarPanel
      class="case-avatar-panel"
      :avatar-status="avatarPanelStatus"
      :subtitle="avatarState.subtitle"
      :connected="avatarState.ready"
      :collapsed="avatarCollapsed"
    >
      <AvatarContainer />
    </AvatarPanel>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";
import AvatarContainer from "../components/AvatarContainer.vue";
import AvatarPanel from "../components/AvatarPanel.vue";
import ChatHeader from "../components/ChatHeader.vue";
import ChatInput from "../components/ChatInput.vue";
import ChatWindow from "../components/ChatWindow.vue";
import StatusBadge from "../components/StatusBadge.vue";
import {
  avatarState,
  normalizeAvatarEmotion,
  playAvatar,
  setAvatarEmotion,
  setAvatarSubtitle,
  stopAvatar,
} from "../services/avatarBridge";
import { buildCaseSettingsPayload, isUnityAvatarEnabled, loadLocalSettings } from "../services/appSettings";
import type { ChatMessage } from "../types/chat";

type CatalogItem = {
  case_id: string;
  title: string;
  category: string;
  difficulty: string;
  summary: string;
};

type CaseApiResponse = {
  session_id: string;
  case_id: string;
  text: string;
  next_question?: string | null;
  state?: string | null;
  next_actions: string[];
  emotion: string;
  path: string[];
  audio_url?: string | null;
};

const catalog = ref<CatalogItem[]>([]);
const catalogLoading = ref(true);
const selectedCaseId = ref("");
const sessionId = ref("");
const starting = ref(false);
const stepping = ref(false);
const freeInput = ref("");
const messages = ref<ChatMessage[]>([]);
const currentQuestion = ref("");
const currentOptions = ref<string[]>([]);
const currentPhase = ref("opening");
const turnCount = ref(0);
const backendOk = ref(true);
const avatarCollapsed = ref(false);
const sidebarCollapsed = ref(typeof window !== "undefined" ? window.innerWidth <= 900 : false);

const currentCaseTitle = computed(() => {
  const found = catalog.value.find((c) => c.case_id === selectedCaseId.value);
  return found?.title || "案件审理中";
});

const phaseLabel = computed(() => {
  const map: Record<string, string> = {
    opening: "开庭阶段",
    trial: "审理阶段",
    verdict: "判决阶段",
  };
  return map[currentPhase.value] || currentPhase.value;
});

const phaseTone = computed<"neutral" | "success" | "warning" | "danger" | "info">(() => {
  if (currentPhase.value === "opening") return "info";
  if (currentPhase.value === "trial") return "warning";
  if (currentPhase.value === "verdict") return "danger";
  return "neutral";
});

const avatarPanelStatus = computed<"idle" | "listening" | "thinking" | "speaking" | "disconnected">(() => {
  if (!avatarState.ready) return "disconnected";
  if (avatarState.isPlaying) return "speaking";
  if (starting.value || stepping.value) return "thinking";
  return "idle";
});

const chatMessages = computed<ChatMessage[]>(() => {
  if (messages.value.length) return messages.value;
  return [
    {
      id: "case-intro",
      role: "assistant",
      text: "请选择左侧案件开始审理。庭审记录会在这里按对话方式展开。",
      citations: [],
    },
  ];
});

function nextId(): string {
  return `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

function scrollToBottom(): void {
  nextTick(() => {
    const node = document.querySelector(".chat-window");
    if (node instanceof HTMLElement) {
      node.scrollTop = node.scrollHeight;
    }
  });
}

function clearDraft(): void {
  freeInput.value = "";
}

function noop(): void {}

function unityAvatarEnabled(): boolean {
  return isUnityAvatarEnabled(loadLocalSettings());
}

function interruptCaseSpeech(): void {
  if (unityAvatarEnabled()) {
    stopAvatar();
  }
}

function resetCase(): void {
  sessionId.value = "";
  selectedCaseId.value = "";
  messages.value = [];
  currentQuestion.value = "";
  currentOptions.value = [];
  turnCount.value = 0;
  currentPhase.value = "opening";
  freeInput.value = "";
  if (unityAvatarEnabled()) {
    stopAvatar();
  }
  setAvatarSubtitle("");
}

onMounted(async () => {
  try {
    const res = await axios.get<CatalogItem[]>("/api/case/catalog");
    catalog.value = res.data;
    backendOk.value = true;
  } catch {
    backendOk.value = false;
    ElMessage.error("无法加载案件库");
  } finally {
    catalogLoading.value = false;
  }
});

async function startCase(): Promise<void> {
  if (!selectedCaseId.value || starting.value) return;
  starting.value = true;
  try {
    stopAvatar();
    const res = await axios.post<CaseApiResponse>("/api/case/start", {
      case_id: selectedCaseId.value,
      ...buildCaseSettingsPayload(),
    });
    sessionId.value = res.data.session_id;
    messages.value = [];
    turnCount.value = 0;
    currentPhase.value = res.data.state || "opening";
    messages.value.push({
      id: nextId(),
      role: "assistant",
      text: res.data.text,
      citations: [],
    });
    currentQuestion.value = res.data.next_question || "";
    currentOptions.value = res.data.next_actions || [];

    const emotion = normalizeAvatarEmotion(res.data.emotion);
    if (unityAvatarEnabled()) {
      setAvatarEmotion(emotion);
    }
    if (res.data.audio_url && unityAvatarEnabled()) {
      playAvatar(res.data.audio_url, res.data.text, emotion);
    } else if (unityAvatarEnabled()) {
      setAvatarSubtitle(res.data.text);
    }

    backendOk.value = true;
    scrollToBottom();
    ElMessage.success("模拟法庭已开庭");
    if (typeof window !== "undefined" && window.innerWidth <= 900) {
      sidebarCollapsed.value = true;
    }
  } catch (err: unknown) {
    backendOk.value = false;
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "开庭失败";
    ElMessage.error(String(detail));
  } finally {
    starting.value = false;
  }
}

async function makeChoice(choice: string): Promise<void> {
  if (avatarState.isPlaying) {
    if (unityAvatarEnabled()) {
      stopAvatar();
    }
  }
  if (!sessionId.value || stepping.value) return;

  if (choice === "选择其他案件") {
    resetCase();
    return;
  }
  if (choice === "再审一次本案") {
    const caseId = selectedCaseId.value;
    resetCase();
    selectedCaseId.value = caseId;
    await startCase();
    return;
  }

  stepping.value = true;
  turnCount.value += 1;
  messages.value.push({ id: nextId(), role: "user", text: choice, citations: [] });
  scrollToBottom();

  try {
    const res = await axios.post<CaseApiResponse>("/api/case/step", {
      session_id: sessionId.value,
      user_choice: choice,
      ...buildCaseSettingsPayload(),
    });
    messages.value.push({ id: nextId(), role: "assistant", text: res.data.text, citations: [] });
    currentQuestion.value = res.data.next_question || "";
    currentOptions.value = res.data.next_actions || [];
    currentPhase.value = res.data.state || "trial";

    const emotion = normalizeAvatarEmotion(res.data.emotion);
    if (unityAvatarEnabled()) {
      setAvatarEmotion(emotion);
    }
    if (res.data.audio_url && unityAvatarEnabled()) {
      playAvatar(res.data.audio_url, res.data.text, emotion);
    } else if (unityAvatarEnabled()) {
      setAvatarSubtitle(res.data.text);
    }

    backendOk.value = true;
    scrollToBottom();
  } catch (err: unknown) {
    backendOk.value = false;
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "审理推进失败";
    ElMessage.error(String(detail));
  } finally {
    stepping.value = false;
  }
}

async function sendFreeInput(): Promise<void> {
  if (avatarState.isPlaying) {
    if (unityAvatarEnabled()) {
      stopAvatar();
    }
  }
  const text = freeInput.value.trim();
  if (!text || stepping.value) return;
  if (!sessionId.value) {
    ElMessage.warning("请先在左侧选择案件并点击“开庭审理”");
    return;
  }

  freeInput.value = "";
  stepping.value = true;
  turnCount.value += 1;
  messages.value.push({ id: nextId(), role: "user", text, citations: [] });
  scrollToBottom();

  try {
    const res = await axios.post<CaseApiResponse>("/api/case/step", {
      session_id: sessionId.value,
      user_input: text,
      ...buildCaseSettingsPayload(),
    });
    messages.value.push({ id: nextId(), role: "assistant", text: res.data.text, citations: [] });
    currentQuestion.value = res.data.next_question || "";
    currentOptions.value = res.data.next_actions || [];
    currentPhase.value = res.data.state || "trial";

    const emotion = normalizeAvatarEmotion(res.data.emotion);
    if (unityAvatarEnabled()) {
      setAvatarEmotion(emotion);
    }
    if (res.data.audio_url && unityAvatarEnabled()) {
      playAvatar(res.data.audio_url, res.data.text, emotion);
    } else if (unityAvatarEnabled()) {
      setAvatarSubtitle(res.data.text);
    }

    backendOk.value = true;
    scrollToBottom();
  } catch (err: unknown) {
    backendOk.value = false;
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "审理推进失败";
    ElMessage.error(String(detail));
  } finally {
    stepping.value = false;
  }
}
</script>

<style scoped>
.case-page {
  height: 100%;
  display: grid;
  grid-template-columns: clamp(250px, 19vw, 330px) minmax(0, 1fr) clamp(280px, 23vw, 380px);
  gap: 12px;
  overflow: hidden;
}

.left-column {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
}

.case-sidebar {
  min-width: 0;
  height: auto;
  min-height: 0;
  overflow: hidden;
  border-radius: 30px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sidebar-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.8rem;
}

.eyebrow {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.74rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.sidebar-head h2 {
  margin: 0.2rem 0 0;
  font-size: 1.16rem;
}

.new-case-btn,
.start-btn,
.toggle-btn,
.home-back-btn {
  border: 0;
  cursor: pointer;
  font-weight: 600;
  width: 100%;
}

.new-case-btn,
.toggle-btn,
.home-back-btn {
  border-radius: 16px;
  padding: 0.8rem 0.95rem;
  background: rgba(241, 247, 255, 0.96);
  color: var(--accent-strong);
  text-align: center;
  text-decoration: none;
}

.start-btn {
  border-radius: 18px;
  padding: 0.95rem 1rem;
  background: linear-gradient(135deg, var(--accent), var(--accent-strong));
  color: #fff;
}

.start-btn:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.catalog-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 0.25rem;
  display: grid;
  align-content: start;
  gap: 0.65rem;
}

.sidebar-actions {
  display: grid;
  gap: 12px;
}

.catalog-item {
  border: 1px solid rgba(134, 157, 188, 0.16);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.62);
  padding: 0.9rem;
  text-align: left;
  display: grid;
  gap: 0.35rem;
  cursor: pointer;
}

.catalog-item.active {
  border-color: rgba(78, 120, 223, 0.34);
  background: rgba(244, 248, 255, 0.96);
  box-shadow: 0 16px 28px rgba(30, 56, 110, 0.1);
}

.catalog-item strong {
  font-size: 0.96rem;
  color: var(--text-primary);
}

.catalog-item span,
.catalog-item small,
.empty-text {
  color: var(--text-muted);
}

.meta-row {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}

.case-main {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 12px;
  height: 100%;
}

.top-nav-row {
  display: flex;
  align-items: stretch;
}

.case-avatar-panel {
  min-width: 0;
}

.case-avatar-panel:deep(.avatar-panel) {
  width: 100%;
  min-width: 0;
  height: 100%;
}

.intro-panel,
.options-panel {
  border-radius: 28px;
  padding: 1rem 1.1rem;
}

.intro-panel h1 {
  margin: 0.25rem 0 0.5rem;
  font-size: clamp(1.3rem, 1.6vw, 1.7rem);
}

.intro-panel p:last-child {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.options-title {
  margin: 0 0 0.8rem;
  font-weight: 600;
  color: var(--text-primary);
}

.options-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.case-main :deep(.input-toolbar) {
  flex-wrap: wrap;
  justify-content: flex-start;
  gap: 12px;
}

.case-main :deep(.chat-input .status-badge) {
  min-height: 34px;
}

.option-btn {
  border: 1px solid rgba(125, 151, 194, 0.18);
  background: rgba(246, 249, 255, 0.96);
  color: var(--accent-strong);
  border-radius: 999px;
  padding: 0.62rem 0.9rem;
  cursor: pointer;
}

.option-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.sidebar-mask {
  display: none;
}

.mobile-only {
  display: none;
}

@media (max-width: 1380px) {
  .case-page {
    grid-template-columns: clamp(240px, 22vw, 300px) minmax(0, 1fr) clamp(240px, 26vw, 320px);
  }
}

@media (max-width: 1100px) {
  .case-page {
    grid-template-columns: clamp(230px, 24vw, 280px) minmax(0, 1fr);
  }

  .case-avatar-panel {
    grid-column: 1 / -1;
  }

  .case-avatar-panel:deep(.avatar-panel) {
    height: auto;
  }
}

@media (max-width: 900px) {
  .case-page {
    position: relative;
    display: flex;
    flex-direction: column;
  }

  .left-column {
    display: block;
  }

  .top-nav-row {
    margin-bottom: 12px;
  }

  .case-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 50;
    width: min(84vw, 320px);
    min-width: 0;
    background: rgba(239, 245, 248, 0.94);
    transform: translateX(0);
    transition: transform 0.24s ease;
  }

  .case-sidebar.collapsed {
    transform: translateX(-100%);
  }

  .sidebar-mask {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(8, 18, 34, 0.24);
    z-index: 40;
  }

  .mobile-only {
    display: inline-flex;
  }

  .case-main {
    min-height: 0;
  }
}
</style>
