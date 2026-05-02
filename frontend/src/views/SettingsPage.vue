<template>
  <div class="settings-workspace">
    <section class="settings-panel glass-panel depth-medium">
      <section class="top-nav-row">
        <RouterLink to="/" class="home-back-btn">返回主界面</RouterLink>
      </section>

      <header class="settings-header">
        <div>
          <p class="eyebrow">System Tuning Console</p>
          <h1 class="title">系统设置</h1>
          <p class="hint">设置会保存到本机 localStorage，并随 /api/chat、/api/case 请求发送。</p>
        </div>
        <div class="header-actions">
          <button type="button" class="ghost-btn" :disabled="loading || saving" @click="restoreDefaults">恢复默认</button>
          <button type="button" class="save-btn" :disabled="loading || saving" @click="saveSettings">
            {{ saving ? "保存中..." : loading ? "加载中..." : "保存并应用" }}
          </button>
        </div>
      </header>

      <div v-if="statusText" class="status-line">{{ statusText }}</div>

      <div class="settings-grid">
        <article class="glass-panel depth-soft block">
          <h2>检索策略</h2>

          <label class="field">
            <span>Top K</span>
            <div class="range-wrap">
              <input v-model.number="form.chat_top_k" type="range" min="1" max="12" />
              <strong>{{ form.chat_top_k }}</strong>
            </div>
          </label>

          <label class="switch-row disabled">
            <span>
              混合检索（向量 + 关键词）
              <small>后端当前未启用，固定关闭</small>
            </span>
            <input v-model="form.hybrid_retrieval" type="checkbox" disabled />
          </label>

          <label class="switch-row">
            <span>重排序（Rerank）</span>
            <input v-model="form.enable_rerank" type="checkbox" />
          </label>
        </article>

        <article class="glass-panel depth-soft block">
          <h2>回答守卫</h2>

          <label class="switch-row">
            <span>无本地依据时使用外部来源声明</span>
            <input v-model="form.reject_without_evidence" type="checkbox" />
          </label>

          <label class="switch-row">
            <span>强制 citation 校验</span>
            <input v-model="form.strict_citation_check" type="checkbox" />
          </label>

          <label class="switch-row disabled">
            <span>
              领域外过滤
              <small>安全守卫固定开启，股票预测等问题不会挂弱相关 citation</small>
            </span>
            <input type="checkbox" checked disabled />
          </label>

          <label class="field">
            <span>默认情绪标签</span>
            <select v-model="form.default_emotion" class="field-select">
              <option value="calm">calm</option>
              <option value="supportive">supportive</option>
              <option value="serious">serious</option>
              <option value="warning">warning</option>
            </select>
          </label>
        </article>

        <article class="glass-panel depth-soft block">
          <h2>播报与数字人</h2>

          <label class="switch-row">
            <span>启用 TTS</span>
            <input v-model="form.enable_tts" type="checkbox" />
          </label>

          <label class="switch-row">
            <span>启用 Unity 数字人播报</span>
            <input v-model="form.enable_unity_avatar" type="checkbox" />
          </label>

          <p class="hint compact">关闭 TTS 后后端返回 audio_url=null；关闭 Unity 后前端不调用 SendMessage 播报。</p>
        </article>

        <article class="glass-panel depth-soft block">
          <h2>模型参数</h2>

          <label class="field">
            <span>Temperature</span>
            <div class="range-wrap">
              <input v-model.number="form.temperature" type="range" min="0" max="1" step="0.05" />
              <strong>{{ form.temperature.toFixed(2) }}</strong>
            </div>
          </label>

          <label class="field">
            <span>Max Tokens</span>
            <input v-model.number="form.max_tokens" type="number" min="128" max="4096" class="field-input" />
          </label>

          <div class="read-only-grid">
            <span>Provider</span>
            <strong>{{ form.llm_provider || "mock" }}</strong>
            <span>Model</span>
            <strong>{{ form.model_name || "当前环境未配置" }}</strong>
          </div>
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
                <input v-model="form.knowledge_collection" type="text" class="field-input" />
              </label>

              <label class="field">
                <span>Embedding Provider</span>
                <select v-model="form.embedding_provider" class="field-select">
                  <option value="mock">mock</option>
                  <option value="ark">ark</option>
                  <option value="doubao">doubao</option>
                </select>
              </label>

              <label class="field">
                <span>请求超时（秒）</span>
                <div class="range-wrap">
                  <input v-model.number="form.timeout_sec" type="range" min="5" max="90" />
                  <strong>{{ form.timeout_sec }}s</strong>
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
import { onMounted, reactive, ref } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";
import {
  DEFAULT_APP_SETTINGS,
  type AppSettings,
  loadLocalSettings,
  normalizeSettings,
  resetLocalSettings,
  saveLocalSettings,
} from "../services/appSettings";

const form = reactive<AppSettings>({ ...DEFAULT_APP_SETTINGS });
const showAdvanced = ref(false);
const loading = ref(false);
const saving = ref(false);
const statusText = ref("");

function applyConfig(config: Partial<AppSettings>): void {
  Object.assign(form, normalizeSettings(config));
  form.hybrid_retrieval = false;
}

function buildPayload(): AppSettings {
  return normalizeSettings({ ...form, hybrid_retrieval: false });
}

async function loadSettings(): Promise<void> {
  loading.value = true;
  try {
    const [effective] = await Promise.allSettled([axios.get<AppSettings>("/api/settings/effective")]);
    const backend = effective.status === "fulfilled" ? effective.value.data : {};
    applyConfig({ ...backend, ...loadLocalSettings() });
    statusText.value = "已加载本地设置；后端有效配置用于补齐模型和默认值。";
  } catch {
    applyConfig(loadLocalSettings());
    ElMessage.warning("后端配置读取失败，已使用本地设置");
  } finally {
    loading.value = false;
  }
}

async function saveSettings(): Promise<void> {
  if (saving.value) return;
  saving.value = true;
  const payload = buildPayload();
  try {
    saveLocalSettings(payload);
    const res = await axios.put<AppSettings>("/api/admin/runtime-config", payload);
    applyConfig({ ...res.data, ...payload });
    statusText.value = "已应用：设置已保存到本机，并写入后端运行时配置。";
    ElMessage.success("设置已应用");
  } catch {
    saveLocalSettings(payload);
    applyConfig(payload);
    statusText.value = "已应用到本机；后端配置保存失败，本次请求仍会携带这些设置。";
    ElMessage.warning("后端保存失败，已保存在本机");
  } finally {
    saving.value = false;
  }
}

async function restoreDefaults(): Promise<void> {
  applyConfig(resetLocalSettings());
  await saveSettings();
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

.top-nav-row {
  margin-bottom: 0.75rem;
}

.home-back-btn {
  display: inline-flex;
  text-decoration: none;
  border-radius: 16px;
  padding: 0.72rem 0.95rem;
  background: rgba(241, 247, 255, 0.96);
  color: var(--accent-strong);
  font-weight: 600;
}

.settings-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.8rem;
  margin-bottom: 0.9rem;
}

.header-actions {
  display: flex;
  gap: 0.55rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.eyebrow,
.hint,
.status-line,
.read-only-grid span,
.switch-row small {
  color: var(--text-muted);
}

.eyebrow {
  margin: 0;
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.title {
  margin: 0.1rem 0 0;
  font-size: 1.3rem;
  font-weight: 700;
}

.hint {
  margin: 0.35rem 0 0;
  font-size: 0.8rem;
}

.hint.compact {
  line-height: 1.6;
}

.status-line {
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.46);
  padding: 0.55rem 0.7rem;
  margin-bottom: 0.8rem;
  font-size: 0.82rem;
}

.save-btn,
.ghost-btn {
  border: 0;
  border-radius: 12px;
  padding: 0.52rem 0.86rem;
  cursor: pointer;
}

.save-btn {
  background: linear-gradient(135deg, #266e84, #3e8f9c);
  color: #fff;
}

.ghost-btn {
  background: rgba(255, 255, 255, 0.56);
  color: var(--accent-strong);
}

.save-btn:disabled,
.ghost-btn:disabled {
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
  gap: 0.8rem;
  border-radius: 12px;
  padding: 0.48rem 0.56rem;
  background: rgba(255, 255, 255, 0.34);
}

.switch-row span {
  display: grid;
  gap: 0.15rem;
}

.switch-row.disabled {
  opacity: 0.72;
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

.read-only-grid {
  margin-top: 0.7rem;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.4rem 0.7rem;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.34);
  padding: 0.62rem;
}

.read-only-grid strong {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
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

  .settings-header {
    display: grid;
  }

  .header-actions,
  .settings-grid,
  .advanced-body {
    grid-template-columns: 1fr;
  }

  .header-actions {
    justify-content: stretch;
  }
}
</style>
