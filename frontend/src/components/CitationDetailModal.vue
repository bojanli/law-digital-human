<template>
  <Teleport to="body">
    <Transition name="citation-modal">
      <div v-if="visible" class="modal-layer" @click="emit('close')">
        <section class="modal-panel" role="dialog" aria-modal="true" @click.stop>
          <header class="modal-header">
            <div class="title-block">
              <p class="eyebrow">引用依据</p>
              <h3>{{ title }}</h3>
              <p class="subtitle">{{ subtitle }}</p>
            </div>
            <button type="button" class="close-btn" aria-label="关闭" @click="emit('close')">×</button>
          </header>

          <main class="modal-body">
            <p v-if="loading" class="state-text">正在加载依据内容...</p>
            <p v-else-if="error" class="state-text error">依据内容加载失败，请稍后重试。</p>
            <article v-else class="detail-text">{{ detail?.text || "暂无依据正文。" }}</article>
          </main>

          <footer class="modal-footer">
            <span>{{ sourceType }}</span>
            <span>{{ sourceText }}</span>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from "vue";
import type { Citation, CitationDetail } from "../types/chat";

const props = defineProps<{
  visible: boolean;
  citation: Citation | null;
  detail: CitationDetail | null;
  loading: boolean;
  error: string;
}>();

const emit = defineEmits<{
  close: [];
}>();

const active = computed(() => props.detail || props.citation);
const title = computed(() => {
  const item = active.value;
  if (!item) return "未标注依据";
  if (item.source_type === "case") return item.case_name || item.law_name || "未标注案例名称";
  return item.law_name || "未标注法律名称";
});
const subtitle = computed(() => {
  const item = active.value;
  if (!item) return "标识待补充";
  const parts = [item.article_no, item.section].filter(Boolean);
  if (parts.length) return parts.join(" · ");
  if (item.source_type === "case") return item.case_id ? `案例#${item.case_id}` : "相关案例";
  return "条号待补充";
});
const sourceType = computed(() => active.value?.source_type || "source");
const sourceText = computed(() => active.value?.source || "未标注来源");

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape" && props.visible) {
    emit("close");
  }
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown);
});
</script>

<style scoped>
.modal-layer {
  position: fixed;
  inset: 0;
  z-index: 120;
  display: grid;
  place-items: center;
  padding: 1.5rem;
  background: rgba(22, 38, 64, 0.24);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.modal-panel {
  width: min(720px, 92vw);
  max-height: min(78vh, 720px);
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  overflow: hidden;
  border-radius: 30px;
  border: 1px solid rgba(146, 170, 205, 0.2);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(246, 250, 255, 0.94)),
    rgba(255, 255, 255, 0.92);
  box-shadow:
    0 36px 90px rgba(24, 48, 92, 0.24),
    0 1px 0 rgba(255, 255, 255, 0.9) inset;
  color: var(--text-primary);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.35rem 1.45rem 1rem;
  border-bottom: 1px solid rgba(135, 157, 186, 0.12);
}

.title-block {
  min-width: 0;
}

.eyebrow,
.subtitle,
.modal-footer {
  margin: 0;
  color: var(--text-muted);
}

.eyebrow {
  font-size: 0.78rem;
  font-weight: 700;
}

h3 {
  margin: 0.18rem 0 0.28rem;
  color: var(--text-primary);
  font-size: 1.16rem;
  line-height: 1.35;
}

.subtitle {
  font-size: 0.9rem;
}

.close-btn {
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 50%;
  background: rgba(231, 238, 249, 0.9);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 1.35rem;
  line-height: 1;
  flex: 0 0 auto;
}

.modal-body {
  min-height: 180px;
  overflow: auto;
  padding: 1.25rem 1.45rem;
}

.detail-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
  line-height: 1.85;
}

.state-text {
  margin: 0;
  color: var(--text-muted);
}

.state-text.error {
  color: #9b3f4a;
}

.modal-footer {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.9rem 1.45rem 1.15rem;
  border-top: 1px solid rgba(135, 157, 186, 0.12);
  font-size: 0.82rem;
  word-break: break-word;
}

.citation-modal-enter-active,
.citation-modal-leave-active {
  transition: opacity 0.2s ease;
}

.citation-modal-enter-active .modal-panel,
.citation-modal-leave-active .modal-panel {
  transition: transform 0.22s ease, opacity 0.22s ease;
}

.citation-modal-enter-from,
.citation-modal-leave-to {
  opacity: 0;
}

.citation-modal-enter-from .modal-panel,
.citation-modal-leave-to .modal-panel {
  opacity: 0;
  transform: translateY(10px) scale(0.985);
}

@media (max-width: 640px) {
  .modal-layer {
    padding: 1rem;
  }

  .modal-panel {
    border-radius: 24px;
    max-height: 82vh;
  }

  .modal-header,
  .modal-body,
  .modal-footer {
    padding-left: 1rem;
    padding-right: 1rem;
  }

  .modal-footer {
    display: grid;
  }
}
</style>
