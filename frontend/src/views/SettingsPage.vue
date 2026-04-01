<template>
  <div class="settings-workspace">
    <section class="settings-panel glass-panel depth-medium">
      <header class="settings-header">
        <div>
          <p class="eyebrow">System Tuning Console</p>
          <h1 class="title">系统设置</h1>
        </div>
        <button type="button" class="save-btn" :disabled="loading || saving" @click="saveSettings">
          {{ saving ? "保存中..." : loading ? "加载中..." : "保存参数" }}
        </button>
      </header>

      <div class="settings-grid">
        <article class="glass-panel depth-soft block">
          <h2>检索策略</h2>

          <label class="field">
            <span>Top K</span>
            <div class="range-wrap">
              <input v-model.number="topK" type="range" min="1" max="12" />
              <strong>{{ topK }}</strong>
            </div>
          </label>

          <label class="switch-row">
            <span>混合检索（向量 + 关键词）</span>
            <input v-model="hybridRetrieval" type="checkbox" />
          </label>

          <label class="switch-row">
            <span>重排序（Rerank）</span>
            <input v-model="enableRerank" type="checkbox" />
          </label>
        </article>

        <article class="glass-panel depth-soft block">
          <h2>回答守卫</h2>

          <label class="switch-row">
            <span>启用“无依据拒答”</span>
            <input v-model="rejectWithoutEvidence" type="checkbox" />
          </label>

          <label class="switch-row">
            <span>强制 citation 校验</span>
            <input v-model="strictCitationCheck" type="checkbox" />
          </label>

          <label class="field">
            <span>默认情绪标签</span>
            <select v-model="defaultEmotion" class="field-select">
              <option value="calm">calm</option>
              <option value="supportive">supportive</option>
              <option value="serious">serious</option>
              <option value="warning">warning</option>
            </select>
          </label>
        </article>

        <article class="glass-panel depth-soft block full">
          <header class="advanced-header">
            <h2>高级选项</h2>
            <button type="button" class="ghost-btn" @click="showAdvanced = !showAdvanced">
              {{ showAdvanced ? "收起" : "展开" }}
            </button>
          </header>

          <Transition name="expand">
            <div v-if="showAdvanced" class="advanced-body">
              <label class="field">
                <span>知识库集合</span>
                <input v-model="knowledgeCollection" type="text" class="field-input" />
              </label>

              <label class="field">
                <span>Embedding Provider</span>
                <select v-model="embeddingProvider" class="field-select">
                  <option value="mock">mock</option>
                  <option value="ark">ark</option>
                  <option value="doubao">doubao</option>
                </select>
              </label>

              <label class="field">
                <span>请求超时（秒）</span>
                <div class="range-wrap">
                  <input v-model.number="timeoutSec" type="range" min="5" max="90" />
                  <strong>{{ timeoutSec }}s</strong>
                </div>
              </label>
            </div>
          </Transition>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";

type RuntimeConfig = {
  chat_top_k: number;
  hybrid_retrieval: boolean;
  enable_rerank: boolean;
  reject_without_evidence: boolean;
  strict_citation_check: boolean;
  default_emotion: "calm" | "supportive" | "serious" | "warning";
  knowledge_collection: string;
  embedding_provider: "mock" | "ark" | "doubao";
  timeout_sec: number;
};

const topK = ref(5);
const hybridRetrieval = ref(false);
const enableRerank = ref(true);

const rejectWithoutEvidence = ref(true);
const strictCitationCheck = ref(true);
const defaultEmotion = ref("calm");

const showAdvanced = ref(false);
const knowledgeCollection = ref("laws");
const embeddingProvider = ref("mock");
const timeoutSec = ref(30);
const loading = ref(false);
const saving = ref(false);

function applyConfig(config: RuntimeConfig): void {
  topK.value = config.chat_top_k;
  hybridRetrieval.value = config.hybrid_retrieval;
  enableRerank.value = config.enable_rerank;
  rejectWithoutEvidence.value = config.reject_without_evidence;
  strictCitationCheck.value = config.strict_citation_check;
  defaultEmotion.value = config.default_emotion;
  knowledgeCollection.value = config.knowledge_collection;
  embeddingProvider.value = config.embedding_provider;
  timeoutSec.value = config.timeout_sec;
}

function buildPayload(): RuntimeConfig {
  return {
    chat_top_k: topK.value,
    hybrid_retrieval: hybridRetrieval.value,
    enable_rerank: enableRerank.value,
    reject_without_evidence: rejectWithoutEvidence.value,
    strict_citation_check: strictCitationCheck.value,
    default_emotion: defaultEmotion.value as RuntimeConfig["default_emotion"],
    knowledge_collection: knowledgeCollection.value.trim() || "laws",
    embedding_provider: embeddingProvider.value as RuntimeConfig["embedding_provider"],
    timeout_sec: timeoutSec.value,
  };
}

async function loadSettings(): Promise<void> {
  loading.value = true;
  try {
    const res = await axios.get<RuntimeConfig>("/api/admin/runtime-config");
    applyConfig(res.data);
  } catch {
    ElMessage.error("读取运行时配置失败");
  } finally {
    loading.value = false;
  }
}

async function saveSettings(): Promise<void> {
  if (saving.value) {
    return;
  }
  saving.value = true;
  try {
    const res = await axios.put<RuntimeConfig>("/api/admin/runtime-config", buildPayload());
    applyConfig(res.data);
    ElMessage.success("运行时配置已保存并生效");
  } catch {
    ElMessage.error("保存配置失败");
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void loadSettings();
});
</script>

<style scoped>
.settings-workspace {
  min-height: calc(100vh - 3rem);
  padding: 1.2rem 1rem;
}

.settings-panel {
  width: min(980px, 100%);
  margin-inline: auto;
  border-radius: 28px;
  padding: 1rem;
}

.settings-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.8rem;
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

.save-btn {
  border: 0;
  border-radius: 12px;
  background: linear-gradient(135deg, #266e84, #3e8f9c);
  color: #fff;
  padding: 0.52rem 0.86rem;
  cursor: pointer;
}

.save-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.8rem;
}

.block {
  border-radius: 18px;
  padding: 0.78rem;
}

.block.full {
  grid-column: 1 / -1;
}

.block h2 {
  margin: 0 0 0.68rem;
  color: var(--accent-strong);
  font-size: 0.95rem;
}

.field {
  display: grid;
  gap: 0.34rem;
  margin-top: 0.56rem;
}

.field > span {
  color: var(--text-muted);
  font-size: 0.81rem;
}

.switch-row {
  margin-top: 0.56rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-radius: 12px;
  padding: 0.48rem 0.56rem;
  background: rgba(255, 255, 255, 0.34);
}

.switch-row input {
  width: 18px;
  height: 18px;
}

.field-select,
.field-input {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.4);
  color: var(--text-primary);
  padding: 0.5rem 0.56rem;
}

.range-wrap {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.56rem;
  align-items: center;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.34);
  padding: 0.52rem 0.56rem;
}

.range-wrap strong {
  color: #1f6277;
}

.advanced-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.6rem;
}

.advanced-header h2 {
  margin: 0;
}

.ghost-btn {
  border: 0;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.46);
  color: var(--accent-strong);
  padding: 0.34rem 0.62rem;
  cursor: pointer;
}

.advanced-body {
  margin-top: 0.64rem;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.62rem;
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.24s ease;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 920px) {
  .settings-workspace {
    min-height: auto;
    padding: 0;
  }

  .settings-panel {
    border-radius: 22px;
  }

  .settings-grid {
    grid-template-columns: 1fr;
  }

  .advanced-body {
    grid-template-columns: 1fr;
  }
}
</style>
