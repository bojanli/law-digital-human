<template>
  <div class="case-workspace">
    <section class="case-panel glass-panel depth-medium">
      <header class="case-header">
        <div>
          <p class="eyebrow">Case Simulation Engine</p>
          <h1 class="title">案件模拟</h1>
        </div>
        <span class="session-pill" :class="sessionId ? 'active' : 'idle'">
          {{ sessionId ? `session: ${sessionId}` : "未开始" }}
        </span>
      </header>

      <div class="top-grid">
        <article class="glass-panel depth-soft card">
          <p class="card-title">案件模板</p>
          <select v-model="caseId" class="field-select">
            <option value="rent_deposit_dispute">租房押金纠纷（rent_deposit_dispute）</option>
            <option value="labor_wage_arrears">劳动欠薪纠纷（labor_wage_arrears）</option>
          </select>
          <button type="button" class="primary-btn" :disabled="starting" @click="startCase">
            {{ starting ? "启动中..." : "开始案件模拟" }}
          </button>
        </article>

        <article class="glass-panel depth-soft card">
          <p class="card-title">当前状态</p>
          <dl class="status-list">
            <div>
              <dt>state</dt>
              <dd>{{ current?.state || "-" }}</dd>
            </div>
            <div>
              <dt>next_question</dt>
              <dd>{{ current?.next_question || "-" }}</dd>
            </div>
            <div>
              <dt>missing_slots</dt>
              <dd>{{ (current?.missing_slots || []).join(", ") || "无" }}</dd>
            </div>
            <div>
              <dt>path</dt>
              <dd>{{ (current?.path || []).join(" -> ") || "无" }}</dd>
            </div>
          </dl>
        </article>
      </div>

      <Transition name="fade-slide">
        <article v-if="!sessionId" class="hint-card glass-panel depth-soft">
          请先点击“开始案件模拟”，再进行多轮推进。
        </article>
      </Transition>

      <AvatarContainer class="avatar-inline" />

      <div v-if="sessionId" class="case-main">
        <article class="glass-panel depth-soft card">
          <p class="card-title">流程推进</p>
          <div class="actions">
            <button
              v-for="action in current?.next_actions || []"
              :key="action"
              type="button"
              class="choice-btn"
              :disabled="stepping"
              @click="stepByChoice(action)"
            >
              {{ action }}
            </button>
          </div>

          <div class="input-row">
            <textarea
              v-model="userInput"
              class="field-input"
              placeholder="输入自然语言推进流程（例如：有合同，已搬走，房屋无损坏）"
              :disabled="stepping"
            />
            <button type="button" class="primary-btn" :disabled="stepping || !userInput.trim()" @click="stepByInput">
              {{ stepping ? "提交中..." : "发送输入" }}
            </button>
          </div>
        </article>

        <article class="glass-panel depth-soft card">
          <p class="card-title">消息流</p>
          <div class="timeline">
            <TransitionGroup name="msg-slide" tag="div" class="timeline-list">
              <section
                v-for="(item, idx) in messages"
                :key="`${idx}_${item.state}_${item.text.slice(0, 12)}`"
                class="timeline-item glass-panel"
              >
                <header>
                  <span class="state-tag">{{ item.state || "-" }}</span>
                </header>
                <p class="timeline-text">{{ item.text }}</p>
                <p v-if="item.next_question" class="timeline-next">下一问：{{ item.next_question }}</p>
              </section>
            </TransitionGroup>
          </div>
        </article>

        <EvidenceCard :citations="current?.citations || []" empty-text="当前轮未返回引用依据。" />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";
import EvidenceCard from "../components/EvidenceCard.vue";
import AvatarContainer from "../components/AvatarContainer.vue";
import {
  normalizeAvatarEmotion,
  playAvatar,
  setAvatarEmotion,
  setAvatarSubtitle,
  stopAvatar,
} from "../services/avatarBridge";

type Citation = {
  chunk_id: string;
  law_name?: string | null;
  article_no?: string | null;
  source?: string | null;
};

type CaseResponse = {
  session_id: string;
  case_id: string;
  text: string;
  next_question?: string | null;
  state?: string | null;
  slots: Record<string, unknown>;
  path: string[];
  missing_slots: string[];
  next_actions: string[];
  citations: Citation[];
  emotion: string;
  audio_url?: string | null;
};

const caseId = ref("rent_deposit_dispute");
const sessionId = ref("");
const userInput = ref("");
const starting = ref(false);
const stepping = ref(false);
const current = ref<CaseResponse | null>(null);
const messages = ref<CaseResponse[]>([]);

function pushMessage(resp: CaseResponse): void {
  current.value = resp;
  messages.value.push(resp);

  const emotion = normalizeAvatarEmotion(resp.emotion);
  setAvatarEmotion(emotion);

  if (typeof resp.audio_url === "string" && resp.audio_url.trim()) {
    playAvatar(resp.audio_url, resp.text, emotion);
  } else {
    setAvatarSubtitle(resp.text);
  }
}

async function startCase(): Promise<void> {
  starting.value = true;
  try {
    stopAvatar();
    const res = await axios.post<CaseResponse>("/api/case/start", { case_id: caseId.value });
    sessionId.value = res.data.session_id;
    messages.value = [];
    pushMessage(res.data);
    ElMessage.success("案件模拟已开始");
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "启动失败";
    ElMessage.error(String(detail));
  } finally {
    starting.value = false;
  }
}

async function stepByChoice(choice: string): Promise<void> {
  if (!sessionId.value) {
    return;
  }
  stepping.value = true;
  try {
    const res = await axios.post<CaseResponse>("/api/case/step", {
      session_id: sessionId.value,
      user_choice: choice,
    });
    pushMessage(res.data);
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "推进失败";
    ElMessage.error(String(detail));
  } finally {
    stepping.value = false;
  }
}

async function stepByInput(): Promise<void> {
  if (!sessionId.value) {
    return;
  }
  const text = userInput.value.trim();
  if (!text) {
    ElMessage.warning("请输入内容");
    return;
  }
  stepping.value = true;
  try {
    const res = await axios.post<CaseResponse>("/api/case/step", {
      session_id: sessionId.value,
      user_input: text,
    });
    userInput.value = "";
    pushMessage(res.data);
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "推进失败";
    ElMessage.error(String(detail));
  } finally {
    stepping.value = false;
  }
}
</script>

<style scoped>
.case-workspace {
  position: relative;
  min-height: calc(100vh - 3rem);
  padding: 1.2rem 1rem;
}

.case-panel {
  width: min(980px, 100%);
  margin-inline: auto;
  border-radius: 28px;
  padding: 1rem;
}

.case-header {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: flex-start;
  margin-bottom: 0.9rem;
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

.session-pill {
  border-radius: 999px;
  border: 1px solid transparent;
  padding: 0.28rem 0.68rem;
  font-size: 0.74rem;
  font-weight: 600;
}

.session-pill.active {
  background: rgba(85, 181, 134, 0.2);
  border-color: rgba(85, 181, 134, 0.5);
  color: #1c6d43;
}

.session-pill.idle {
  background: rgba(255, 255, 255, 0.35);
  border-color: rgba(255, 255, 255, 0.2);
  color: var(--text-muted);
}

.top-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.8rem;
}

.card {
  border-radius: 18px;
  padding: 0.72rem;
}

.card-title {
  margin: 0 0 0.46rem;
  color: var(--accent-strong);
  font-size: 0.9rem;
  font-weight: 600;
}

.field-select,
.field-input {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.24);
  background: rgba(255, 255, 255, 0.4);
  border-radius: 12px;
  color: var(--text-primary);
}

.field-select {
  padding: 0.5rem 0.56rem;
}

.field-input {
  min-height: 88px;
  padding: 0.56rem 0.62rem;
  resize: vertical;
}

.primary-btn {
  margin-top: 0.6rem;
  border: 0;
  border-radius: 12px;
  background: linear-gradient(135deg, #266e84, #3e8f9c);
  color: #fff;
  padding: 0.52rem 0.86rem;
  cursor: pointer;
}

.primary-btn:disabled {
  opacity: 0.64;
  cursor: not-allowed;
}

.status-list {
  margin: 0;
  display: grid;
  gap: 0.38rem;
}

.status-list div {
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.34);
  padding: 0.46rem 0.54rem;
}

.status-list dt {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.status-list dd {
  margin: 0.12rem 0 0;
  font-size: 0.84rem;
  word-break: break-word;
}

.hint-card {
  margin-top: 0.8rem;
  border-radius: 14px;
  padding: 0.68rem 0.76rem;
  color: var(--text-muted);
}

.avatar-inline {
  margin-top: 0.8rem;
}

.case-main {
  margin-top: 0.8rem;
  display: grid;
  gap: 0.8rem;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.42rem;
  margin-bottom: 0.62rem;
}

.choice-btn {
  border: 1px solid rgba(255, 255, 255, 0.3);
  background: rgba(255, 255, 255, 0.42);
  color: #174569;
  border-radius: 999px;
  padding: 0.3rem 0.68rem;
  cursor: pointer;
}

.choice-btn:disabled {
  opacity: 0.64;
  cursor: not-allowed;
}

.input-row {
  display: grid;
  gap: 0.5rem;
}

.timeline {
  max-height: 36vh;
  overflow: auto;
}

.timeline-list {
  display: grid;
  gap: 0.56rem;
}

.timeline-item {
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.32);
  padding: 0.56rem;
}

.state-tag {
  display: inline-block;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.45);
  color: #1f6277;
  font-size: 0.72rem;
  padding: 0.18rem 0.48rem;
}

.timeline-text {
  margin: 0.36rem 0 0;
  white-space: pre-wrap;
}

.timeline-next {
  margin: 0.36rem 0 0;
  color: var(--text-muted);
}

.fade-slide-enter-active,
.fade-slide-leave-active,
.msg-slide-enter-active,
.msg-slide-leave-active {
  transition: all 0.24s ease;
}

.fade-slide-enter-from,
.fade-slide-leave-to,
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

  .case-panel {
    border-radius: 22px;
  }

  .top-grid {
    grid-template-columns: 1fr;
  }
}
</style>
