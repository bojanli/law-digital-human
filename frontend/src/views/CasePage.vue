<template>
  <div class="case-workspace">
    <!-- 阶段 1: 案件选择 -->
    <Transition name="fade-slide">
      <section v-if="!sessionId" class="case-panel glass-panel depth-medium">
        <header class="case-header">
          <div>
            <p class="eyebrow">Mock Court Simulation</p>
            <h1 class="title">⚖️ 模拟法庭</h1>
          </div>
          <span class="mode-pill">选择案件</span>
        </header>

        <p class="intro-text">
          欢迎来到模拟法庭！选择一件著名案件，你将以<strong>法官</strong>的身份亲自主持审理。
          审查证据、听取辩论、做出判决——你的选择将导向不同的结局。
        </p>

        <div v-if="catalogLoading" class="loading-hint">正在加载案件库...</div>

        <div v-else class="case-grid">
          <article
            v-for="c in catalog"
            :key="c.case_id"
            class="case-card glass-panel depth-soft"
            :class="{ selected: selectedCaseId === c.case_id }"
            @click="selectedCaseId = c.case_id"
          >
            <div class="card-top">
              <span class="category-tag">{{ c.category }}</span>
              <span class="difficulty-tag">{{ c.difficulty }}</span>
            </div>
            <h2 class="case-title">{{ c.title }}</h2>
            <p class="case-summary">{{ c.summary }}</p>
          </article>
        </div>

        <div v-if="selectedCaseId" class="start-bar">
          <button
            type="button"
            class="start-btn"
            :disabled="starting"
            @click="startCase"
          >
            {{ starting ? "正在组建法庭..." : "🔨 开庭审理" }}
          </button>
        </div>
      </section>
    </Transition>

    <!-- 阶段 2: 法庭审理 -->
    <Transition name="fade-slide">
      <section v-if="sessionId" class="court-panel glass-panel depth-medium">
        <header class="court-header">
          <div>
            <p class="eyebrow">正在审理</p>
            <h1 class="title">{{ currentCaseTitle }}</h1>
          </div>
          <div class="header-right">
            <span class="turn-pill">第 {{ turnCount }} 轮</span>
            <span class="phase-pill" :class="currentPhase">{{ phaseLabel }}</span>
          </div>
        </header>

        <!-- 消息流 -->
        <div class="court-stream" ref="streamRef">
          <TransitionGroup name="msg-slide" tag="div" class="message-list">
            <article
              v-for="msg in messages"
              :key="msg.id"
              class="court-message"
              :class="msg.role"
            >
              <div class="msg-avatar">{{ msg.role === "user" ? "👨‍⚖️" : "📋" }}</div>
              <div class="msg-content glass-panel depth-soft" :class="msg.role === 'user' ? 'msg-judge' : 'msg-court'">
                <p class="msg-label">{{ msg.role === "user" ? "法官 (你)" : "法庭记录" }}</p>
                <p class="msg-text">{{ msg.text }}</p>
              </div>
            </article>
          </TransitionGroup>
        </div>

        <!-- 选项按钮 -->
        <div v-if="currentQuestion" class="options-section glass-panel depth-soft">
          <p class="options-question">{{ currentQuestion }}</p>
          <div class="options-grid">
            <button
              v-for="(opt, idx) in currentOptions"
              :key="idx"
              type="button"
              class="option-btn"
              :disabled="stepping"
              @click="makeChoice(opt)"
            >
              {{ opt }}
            </button>
          </div>
        </div>

        <!-- 自由输入 -->
        <form class="composer glass-panel depth-soft" @submit.prevent="sendFreeInput">
          <textarea
            v-model="freeInput"
            class="composer-input"
            placeholder="也可以自由输入你的审判指令..."
            :disabled="stepping"
          />
          <button type="submit" class="send-btn" :disabled="stepping || !freeInput.trim()">
            {{ stepping ? "处理中..." : "发送" }}
          </button>
        </form>

        <!-- 退出按钮 -->
        <button type="button" class="exit-btn" @click="exitCase">退出审理，选择其他案件</button>
      </section>
    </Transition>

    <AvatarContainer class="avatar-dock" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";
import AvatarContainer from "../components/AvatarContainer.vue";
import {
  normalizeAvatarEmotion,
  playAvatar,
  setAvatarEmotion,
  setAvatarSubtitle,
  stopAvatar,
} from "../services/avatarBridge";

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

type CourtMessage = {
  id: string;
  role: "user" | "court";
  text: string;
};

const catalog = ref<CatalogItem[]>([]);
const catalogLoading = ref(true);
const selectedCaseId = ref("");
const sessionId = ref("");
const starting = ref(false);
const stepping = ref(false);
const freeInput = ref("");
const messages = ref<CourtMessage[]>([]);
const currentQuestion = ref("");
const currentOptions = ref<string[]>([]);
const currentPhase = ref("opening");
const turnCount = ref(0);
const streamRef = ref<HTMLElement | null>(null);

const currentCaseTitle = computed(() => {
  const found = catalog.value.find((c) => c.case_id === selectedCaseId.value);
  return found?.title || "案件审理中";
});

const phaseLabel = computed(() => {
  const map: Record<string, string> = {
    opening: "📖 开庭阶段",
    trial: "⚖️ 审理阶段",
    verdict: "🔨 判决阶段",
  };
  return map[currentPhase.value] || currentPhase.value;
});

function nextId(): string {
  return `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

function scrollToBottom(): void {
  nextTick(() => {
    if (streamRef.value) {
      streamRef.value.scrollTop = streamRef.value.scrollHeight;
    }
  });
}

onMounted(async () => {
  try {
    const res = await axios.get<CatalogItem[]>("/api/case/catalog");
    catalog.value = res.data;
  } catch {
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
    });
    sessionId.value = res.data.session_id;
    messages.value = [];
    turnCount.value = 0;
    currentPhase.value = res.data.state || "opening";

    messages.value.push({
      id: nextId(),
      role: "court",
      text: res.data.text,
    });

    currentQuestion.value = res.data.next_question || "";
    currentOptions.value = res.data.next_actions || [];

    const emotion = normalizeAvatarEmotion(res.data.emotion);
    setAvatarEmotion(emotion);
    if (res.data.audio_url) {
      playAvatar(res.data.audio_url, res.data.text, emotion);
    } else {
      setAvatarSubtitle(res.data.text);
    }

    scrollToBottom();
    ElMessage.success("模拟法庭已开庭 ⚖️");
  } catch (err: unknown) {
    const detail =
      (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail || "开庭失败";
    ElMessage.error(String(detail));
  } finally {
    starting.value = false;
  }
}

async function makeChoice(choice: string): Promise<void> {
  if (!sessionId.value || stepping.value) return;

  // 特殊处理"选择其他案件"
  if (choice === "选择其他案件") {
    exitCase();
    return;
  }
  if (choice === "再审一次本案") {
    const caseId = selectedCaseId.value;
    exitCase();
    selectedCaseId.value = caseId;
    await startCase();
    return;
  }

  stepping.value = true;
  turnCount.value += 1;

  messages.value.push({
    id: nextId(),
    role: "user",
    text: choice,
  });
  scrollToBottom();

  try {
    const res = await axios.post<CaseApiResponse>("/api/case/step", {
      session_id: sessionId.value,
      user_choice: choice,
    });

    messages.value.push({
      id: nextId(),
      role: "court",
      text: res.data.text,
    });

    currentQuestion.value = res.data.next_question || "";
    currentOptions.value = res.data.next_actions || [];
    currentPhase.value = res.data.state || "trial";

    const emotion = normalizeAvatarEmotion(res.data.emotion);
    setAvatarEmotion(emotion);
    if (res.data.audio_url) {
      playAvatar(res.data.audio_url, res.data.text, emotion);
    } else {
      setAvatarSubtitle(res.data.text);
    }

    scrollToBottom();
  } catch (err: unknown) {
    const detail =
      (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail || "审理推进失败";
    ElMessage.error(String(detail));
  } finally {
    stepping.value = false;
  }
}

async function sendFreeInput(): Promise<void> {
  const text = freeInput.value.trim();
  if (!text || !sessionId.value) return;
  freeInput.value = "";

  stepping.value = true;
  turnCount.value += 1;

  messages.value.push({
    id: nextId(),
    role: "user",
    text,
  });
  scrollToBottom();

  try {
    const res = await axios.post<CaseApiResponse>("/api/case/step", {
      session_id: sessionId.value,
      user_input: text,
    });

    messages.value.push({
      id: nextId(),
      role: "court",
      text: res.data.text,
    });

    currentQuestion.value = res.data.next_question || "";
    currentOptions.value = res.data.next_actions || [];
    currentPhase.value = res.data.state || "trial";

    const emotion = normalizeAvatarEmotion(res.data.emotion);
    setAvatarEmotion(emotion);
    scrollToBottom();
  } catch (err: unknown) {
    const detail =
      (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail || "审理推进失败";
    ElMessage.error(String(detail));
  } finally {
    stepping.value = false;
  }
}

function exitCase(): void {
  sessionId.value = "";
  selectedCaseId.value = "";
  messages.value = [];
  currentQuestion.value = "";
  currentOptions.value = [];
  turnCount.value = 0;
  currentPhase.value = "opening";
  stopAvatar();
}
</script>

<style scoped>
.case-workspace {
  position: relative;
  min-height: calc(100vh - 3rem);
  padding: 1.2rem 1rem;
  display: flex;
  justify-content: center;
}

/* ── 案件选择面板 ── */
.case-panel {
  width: min(980px, 100%);
  border-radius: 28px;
  padding: 1.2rem;
}

.case-header,
.court-header {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: flex-start;
  margin-bottom: 0.6rem;
}

.eyebrow {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.title {
  margin: 0.1rem 0 0;
  font-size: 1.3rem;
  font-weight: 700;
}

.mode-pill,
.turn-pill,
.phase-pill {
  border-radius: 999px;
  padding: 0.28rem 0.68rem;
  font-size: 0.74rem;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: var(--text-muted);
}

.phase-pill.opening { background: rgba(100, 150, 255, 0.15); color: #2856a6; }
.phase-pill.trial { background: rgba(255, 165, 0, 0.15); color: #a06520; }
.phase-pill.verdict { background: rgba(220, 50, 50, 0.15); color: #8b2020; }

.header-right {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.intro-text {
  color: var(--text-muted);
  font-size: 0.9rem;
  line-height: 1.6;
  margin: 0 0 1rem;
}

.loading-hint {
  text-align: center;
  color: var(--text-muted);
  padding: 2rem;
}

/* ── 案件选择卡片 ── */
.case-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.8rem;
  margin-bottom: 1rem;
}

.case-card {
  border-radius: 18px;
  padding: 0.9rem;
  cursor: pointer;
  transition: all 0.25s ease;
  border: 2px solid transparent;
}

.case-card:hover {
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.45);
}

.case-card.selected {
  border-color: var(--accent);
  background: rgba(255, 255, 255, 0.5);
  box-shadow: 0 0 0 3px rgba(47, 127, 143, 0.15);
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.category-tag {
  background: rgba(47, 127, 143, 0.15);
  color: var(--accent);
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.18rem 0.5rem;
  border-radius: 999px;
}

.difficulty-tag {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.case-title {
  margin: 0 0 0.4rem;
  font-size: 1rem;
  font-weight: 700;
}

.case-summary {
  margin: 0;
  font-size: 0.82rem;
  color: var(--text-muted);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.start-bar {
  text-align: center;
}

.start-btn {
  border: 0;
  border-radius: 14px;
  background: linear-gradient(135deg, #266e84, #3e8f9c);
  color: #fff;
  padding: 0.7rem 2rem;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.25s ease;
}

.start-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(38, 110, 132, 0.3);
}

.start-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ── 法庭审理面板 ── */
.court-panel {
  width: min(800px, 100%);
  border-radius: 28px;
  padding: 1rem;
  display: grid;
  gap: 0.8rem;
  grid-template-rows: auto 1fr auto auto auto;
}

.court-stream {
  min-height: 0;
  max-height: min(50vh, 480px);
  overflow: auto;
  padding-right: 0.2rem;
}

.message-list {
  display: grid;
  gap: 0.7rem;
}

.court-message {
  display: flex;
  gap: 0.6rem;
  align-items: flex-start;
}

.court-message.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  font-size: 1.5rem;
  flex-shrink: 0;
  width: 2.2rem;
  height: 2.2rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.msg-content {
  max-width: min(80%, 560px);
  border-radius: 18px;
  padding: 0.7rem 0.85rem;
}

.msg-court {
  background: rgba(255, 255, 255, 0.3);
}

.msg-judge {
  background: rgba(47, 127, 143, 0.12);
  border: 1px solid rgba(47, 127, 143, 0.2);
}

.msg-label {
  margin: 0 0 0.2rem;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-muted);
}

.msg-text {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.6;
}

/* ── 选项按钮 ── */
.options-section {
  border-radius: 18px;
  padding: 0.8rem;
}

.options-question {
  margin: 0 0 0.5rem;
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-primary);
}

.options-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.option-btn {
  border: 1px solid rgba(47, 127, 143, 0.3);
  background: rgba(255, 255, 255, 0.5);
  color: var(--text-primary);
  border-radius: 12px;
  padding: 0.52rem 0.9rem;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.option-btn:hover:not(:disabled) {
  background: rgba(47, 127, 143, 0.1);
  border-color: var(--accent);
  transform: translateY(-1px);
}

.option-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── 自由输入 ── */
.composer {
  border-radius: 18px;
  padding: 0.6rem;
  display: flex;
  gap: 0.6rem;
  align-items: flex-end;
}

.composer-input {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 14px;
  resize: none;
  min-height: 48px;
  max-height: 120px;
  padding: 0.5rem 0.6rem;
  background: rgba(255, 255, 255, 0.37);
  color: var(--text-primary);
  font: inherit;
}

.composer-input:focus {
  outline: 2px solid rgba(31, 98, 119, 0.35);
}

.send-btn {
  border: 0;
  background: linear-gradient(135deg, #266e84, #3e8f9c);
  color: #fff;
  border-radius: 12px;
  padding: 0.5rem 0.8rem;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.send-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.exit-btn {
  border: 1px solid rgba(255, 255, 255, 0.3);
  background: rgba(255, 255, 255, 0.2);
  color: var(--text-muted);
  border-radius: 12px;
  padding: 0.45rem 0.8rem;
  cursor: pointer;
  font-size: 0.82rem;
  transition: all 0.2s ease;
  text-align: center;
}

.exit-btn:hover {
  background: rgba(255, 255, 255, 0.4);
}

/* ── Avatar ── */
.avatar-dock {
  position: fixed;
  right: 1.5rem;
  bottom: 1.2rem;
  width: 17rem;
  z-index: 30;
}

/* ── 动画 ── */
.fade-slide-enter-active,
.fade-slide-leave-active,
.msg-slide-enter-active,
.msg-slide-leave-active {
  transition: all 0.3s ease;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(12px);
}

.msg-slide-enter-from,
.msg-slide-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 920px) {
  .case-workspace {
    min-height: auto;
    padding: 0;
  }

  .case-panel,
  .court-panel {
    border-radius: 22px;
  }

  .case-grid {
    grid-template-columns: 1fr;
  }

  .avatar-dock {
    position: fixed;
    left: 1rem;
    right: 1rem;
    width: auto;
    bottom: 1rem;
    z-index: 45;
  }
}
</style>
