<template>
  <div class="chat-workspace">
    <section class="chat-panel glass-panel depth-medium">
      <header class="chat-header">
        <div>
          <p class="eyebrow">Digital Law Copilot</p>
          <h1 class="title">法律问答</h1>
        </div>
        <span class="status-pill" :class="backendOk ? 'online' : 'offline'">
          {{ backendOk ? "Backend Online" : "Backend Unstable" }}
        </span>
      </header>

      <div class="quick-row">
        <button
          v-for="prompt in quickPrompts"
          :key="prompt"
          type="button"
          class="quick-chip"
          @click="applyPrompt(prompt)"
        >
          {{ prompt }}
        </button>
      </div>

      <div class="stream">
        <TransitionGroup name="message-slide" tag="div" class="message-list">
          <article v-for="message in messages" :key="message.id" class="message-row" :class="message.role">
            <div class="bubble glass-panel depth-soft" :class="message.role === 'user' ? 'bubble-user' : 'bubble-ai'">
              <p class="bubble-text">{{ message.text }}</p>
            </div>
          </article>
        </TransitionGroup>
      </div>

      <form class="composer glass-panel depth-soft" @submit.prevent="sendMessage">
        <textarea
          v-model="draft"
          class="composer-input"
          placeholder="输入问题，例如：房东不退押金我该怎么办？"
          :disabled="loading"
        />
        <button type="submit" class="send-btn" :disabled="loading || !draft.trim()">
          {{ loading ? "发送中..." : "发送" }}
        </button>
      </form>

      <EvidenceCard :citations="latestCitations" empty-text="当前会话还没有可核验引用依据。" />
    </section>

    <Transition name="float-panel">
      <aside v-if="showReasoningPanel" class="reasoning-panel glass-panel depth-medium">
        <header class="reasoning-header">
          <h2>思维签名</h2>
          <button type="button" class="panel-toggle" @click="showReasoningPanel = false">收起</button>
        </header>

        <section class="reasoning-block">
          <h3>事实提取</h3>
          <ul>
            <li v-for="item in latestReasoning.facts" :key="`fact_${item}`">{{ item }}</li>
          </ul>
        </section>

        <section class="reasoning-block">
          <h3>规则匹配</h3>
          <ul>
            <li v-for="item in latestReasoning.rules" :key="`rule_${item}`">{{ item }}</li>
          </ul>
        </section>

        <section class="reasoning-block">
          <h3>风险评估</h3>
          <ul>
            <li v-for="item in latestReasoning.risks" :key="`risk_${item}`">{{ item }}</li>
          </ul>
        </section>
      </aside>
    </Transition>

    <button
      v-if="!showReasoningPanel"
      type="button"
      class="reasoning-fab glass-panel depth-medium"
      @click="showReasoningPanel = true"
    >
      展开思维签名
    </button>

    <AvatarContainer class="avatar-dock" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import axios from "axios";
import EvidenceCard from "../components/EvidenceCard.vue";
import AvatarContainer from "../components/AvatarContainer.vue";
import { normalizeAvatarEmotion, playAvatar, setAvatarEmotion } from "../services/avatarBridge";

type Citation = {
  chunk_id: string;
  law_name?: string | null;
  article_no?: string | null;
  section?: string | null;
  source?: string | null;
};

type ReasoningSignature = {
  facts: string[];
  rules: string[];
  risks: string[];
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations: Citation[];
  reasoning?: ReasoningSignature;
};

type ChatApiResponse = {
  answer_json?: Record<string, unknown>;
  audio_url?: string | null;
};

const quickPrompts = [
  "房东不退押金怎么办？",
  "兼职被拖欠工资如何维权？",
  "网购到假货如何取证？",
];

const sessionId = ref(`web_${Date.now().toString(36)}`);
const draft = ref("");
const loading = ref(false);
const backendOk = ref(true);
const showReasoningPanel = ref(true);

const messages = ref<ChatMessage[]>([
  {
    id: "boot",
    role: "assistant",
    text: "你好，我是普法数字助手。你可以描述事实，我会给出可核验的法律依据。",
    citations: [],
    reasoning: {
      facts: ["等待用户输入事实。"],
      rules: ["检索法条并执行引用校验策略。"],
      risks: ["事实不完整时，仅输出谨慎结论。"],
    },
  },
]);

const latestReasoning = computed<ReasoningSignature>(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const message = messages.value[i];
    if (!message) {
      continue;
    }
    if (message.role === "assistant" && message.reasoning) {
      return message.reasoning;
    }
  }
  return {
    facts: ["等待模型推理输出。"],
    rules: ["暂无规则匹配结果。"],
    risks: ["暂无风险评估结果。"],
  };
});

const latestCitations = computed<Citation[]>(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const message = messages.value[i];
    if (!message) {
      continue;
    }
    if (message.role === "assistant" && message.citations.length) {
      return message.citations;
    }
  }
  return [];
});

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function toCitationList(value: unknown): Citation[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const output: Citation[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const raw = item as Record<string, unknown>;
    const chunkId = typeof raw.chunk_id === "string" ? raw.chunk_id.trim() : "";
    if (!chunkId) {
      continue;
    }
    output.push({
      chunk_id: chunkId,
      law_name: typeof raw.law_name === "string" ? raw.law_name : null,
      article_no: typeof raw.article_no === "string" ? raw.article_no : null,
      section: typeof raw.section === "string" ? raw.section : null,
      source: typeof raw.source === "string" ? raw.source : null,
    });
  }
  return output;
}

function buildReasoning(answerJson: Record<string, unknown>, citations: Citation[]): ReasoningSignature {
  const facts = toStringList(answerJson.assumptions);
  const analysis = toStringList(answerJson.analysis);
  const followUps = toStringList(answerJson.follow_up_questions);
  const rules = citations.map((c) => `${c.law_name || "法律条文"} ${c.article_no || ""}`.trim());

  return {
    facts: (facts.length ? facts : analysis).slice(0, 3).map((item) => item.trim()),
    rules: (rules.length ? rules : ["当前轮未命中可核验法条，建议补充证据。"]).slice(0, 3),
    risks: (followUps.length ? followUps.map((item) => `待确认：${item}`) : ["请核对时间线与证据来源，避免事实偏差。"]).slice(0, 3),
  };
}

function composeAssistantText(answerJson: Record<string, unknown>, citations: Citation[]): string {
  const rawConclusion = answerJson.conclusion;
  const conclusion =
    typeof rawConclusion === "string" && rawConclusion.trim()
      ? rawConclusion.trim()
      : "当前暂无法输出稳定结论，请补充事实后继续。";
  const actions = toStringList(answerJson.actions).slice(0, 2);
  const lines = [conclusion];

  if (actions.length) {
    lines.push(`建议：${actions.join("；")}`);
  }
  if (citations.length) {
    lines.push(`本轮已引用 ${citations.length} 条依据。`);
  }
  return lines.join("\n");
}

function nextId(): string {
  return `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

function applyPrompt(prompt: string): void {
  draft.value = prompt;
}

async function sendMessage(): Promise<void> {
  const input = draft.value.trim();
  if (!input || loading.value) {
    return;
  }

  messages.value.push({
    id: nextId(),
    role: "user",
    text: input,
    citations: [],
  });
  draft.value = "";
  loading.value = true;

  try {
    const res = await axios.post<ChatApiResponse>("/api/chat", {
      session_id: sessionId.value,
      text: input,
      mode: "chat",
      case_state: null,
    });

    const answerJson = (res.data?.answer_json || {}) as Record<string, unknown>;
    const citations = toCitationList(answerJson.citations);
    const reasoning = buildReasoning(answerJson, citations);
    const assistantText = composeAssistantText(answerJson, citations);
    const emotion = normalizeAvatarEmotion(answerJson.emotion);

    messages.value.push({
      id: nextId(),
      role: "assistant",
      text: assistantText,
      citations,
      reasoning,
    });

    setAvatarEmotion(emotion);
    if (typeof res.data?.audio_url === "string" && res.data.audio_url.trim()) {
      playAvatar(res.data.audio_url, assistantText, emotion);
    }

    backendOk.value = true;
  } catch {
    backendOk.value = false;
    setAvatarEmotion("serious");
    messages.value.push({
      id: nextId(),
      role: "assistant",
      text: "后端暂时不可用，我先记录你的问题。稍后重试或切换到案件模拟继续。",
      citations: [],
      reasoning: {
        facts: ["用户已提交问题，等待服务恢复。"],
        rules: ["当前未能获取检索结果。"],
        risks: ["无法生成可核验引用，暂停结论输出。"],
      },
    });
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.chat-workspace {
  position: relative;
  min-height: calc(100vh - 3rem);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.2rem 20rem 1.2rem 2rem;
}

.chat-panel {
  width: min(760px, 100%);
  border-radius: 28px;
  padding: 1rem;
  display: grid;
  gap: 0.9rem;
  grid-template-rows: auto auto minmax(280px, 1fr) auto;
}

.chat-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.8rem;
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

.status-pill {
  border-radius: 999px;
  border: 1px solid transparent;
  padding: 0.26rem 0.66rem;
  font-size: 0.74rem;
  font-weight: 600;
  white-space: nowrap;
}

.status-pill.online {
  background: rgba(85, 181, 134, 0.2);
  border-color: rgba(85, 181, 134, 0.5);
  color: #1c6d43;
}

.status-pill.offline {
  background: rgba(226, 107, 106, 0.2);
  border-color: rgba(226, 107, 106, 0.5);
  color: #922e2a;
}

.quick-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.quick-chip {
  border: 1px solid rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.28);
  border-radius: 999px;
  padding: 0.33rem 0.72rem;
  color: var(--accent-strong);
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease;
}

.quick-chip:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.45);
}

.stream {
  min-height: 0;
  max-height: min(56vh, 520px);
  overflow: auto;
  padding-right: 0.2rem;
}

.message-list {
  display: grid;
  gap: 0.7rem;
}

.message-row {
  display: flex;
}

.message-row.user {
  justify-content: flex-end;
}

.bubble {
  max-width: min(78%, 540px);
  border-radius: 20px;
  padding: 0.72rem 0.86rem;
}

.bubble-ai {
  background: rgba(255, 255, 255, 0.3);
}

.bubble-user {
  background: rgba(255, 255, 255, 0.5);
}

.bubble-text {
  margin: 0;
  white-space: pre-wrap;
}

.composer {
  border-radius: 18px;
  padding: 0.64rem;
  display: flex;
  gap: 0.62rem;
  align-items: flex-end;
}

.composer-input {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 14px;
  resize: none;
  min-height: 60px;
  max-height: 170px;
  padding: 0.55rem 0.66rem;
  background: rgba(255, 255, 255, 0.37);
  color: var(--text-primary);
}

.composer-input:focus {
  outline: 2px solid rgba(31, 98, 119, 0.35);
}

.send-btn {
  border: 0;
  background: linear-gradient(135deg, #266e84, #3e8f9c);
  color: #fff;
  border-radius: 12px;
  padding: 0.58rem 0.96rem;
  cursor: pointer;
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.send-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.reasoning-panel {
  position: absolute;
  right: 1.5rem;
  top: 1.2rem;
  width: 17rem;
  border-radius: 22px;
  padding: 0.85rem;
}

.reasoning-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  margin-bottom: 0.4rem;
}

.reasoning-header h2 {
  margin: 0;
  font-size: 0.97rem;
}

.panel-toggle {
  border: 0;
  background: rgba(255, 255, 255, 0.48);
  color: #1f6277;
  border-radius: 999px;
  padding: 0.2rem 0.58rem;
  cursor: pointer;
}

.reasoning-block {
  background: rgba(255, 255, 255, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 14px;
  padding: 0.48rem 0.58rem;
  margin-top: 0.5rem;
}

.reasoning-block h3 {
  margin: 0 0 0.25rem;
  font-size: 0.81rem;
  color: var(--accent-strong);
}

.reasoning-block ul {
  margin: 0;
  padding-left: 1rem;
  display: grid;
  gap: 0.2rem;
  font-size: 0.8rem;
}

.reasoning-fab {
  position: absolute;
  right: 1.5rem;
  top: 1.4rem;
  border: 0;
  border-radius: 999px;
  padding: 0.45rem 0.8rem;
  color: var(--accent-strong);
  cursor: pointer;
}

.avatar-dock {
  position: absolute;
  right: 1.5rem;
  bottom: 1.2rem;
  width: 17rem;
  z-index: 30;
}

.float-panel-enter-active,
.float-panel-leave-active,
.message-slide-enter-active,
.message-slide-leave-active {
  transition: all 0.24s ease;
}

.float-panel-enter-from,
.float-panel-leave-to {
  opacity: 0;
  transform: translateX(14px);
}

.message-slide-enter-from,
.message-slide-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 1180px) {
  .chat-workspace {
    padding-right: 1.2rem;
  }

  .reasoning-panel,
  .reasoning-fab,
  .avatar-dock {
    right: 0.8rem;
  }
}

@media (max-width: 900px) {
  .chat-workspace {
    min-height: auto;
    padding: 0;
  }

  .chat-panel {
    width: 100%;
    border-radius: 22px;
    min-height: 70vh;
  }

  .reasoning-panel {
    position: fixed;
    left: 1rem;
    right: 1rem;
    top: auto;
    bottom: 6.6rem;
    width: auto;
    max-height: 46vh;
    overflow: auto;
    z-index: 50;
  }

  .reasoning-fab {
    position: fixed;
    right: 1rem;
    bottom: 8.4rem;
    z-index: 50;
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
