<template>
  <section class="evidence-panel">
    <div v-if="citations.length" class="chip-list">
      <button
        v-for="citation in citations"
        :key="citation.chunk_id"
        type="button"
        class="citation-chip"
        @click="emit('selectCitation', citation)"
      >
        <span>{{ displayTitle(citation) }}</span>
        <small>{{ displayIndex(citation) }}</small>
      </button>
    </div>
    <p v-else class="empty-text">{{ emptyText }}</p>
  </section>
</template>

<script setup lang="ts">
import type { Citation } from "../types/chat";

withDefaults(
  defineProps<{
    citations: Citation[];
    emptyText?: string;
  }>(),
  {
    emptyText: "当前回答未返回可核验引用依据。",
  },
);

const emit = defineEmits<{
  selectCitation: [citation: Citation];
}>();

function displayTitle(citation: Citation | null): string {
  if (!citation) return "未标注依据";
  if (citation.source_type === "case") return citation.case_name || citation.law_name || "未标注案例名称";
  return citation.law_name || "未标注法律名称";
}

function displayIndex(citation: Citation | null): string {
  if (!citation) return "标识待补充";
  if (citation.source_type === "case") return citation.case_id ? `案例#${citation.case_id}` : "相关案例";
  return citation.article_no || "条号待补充";
}
</script>

<style scoped>
.evidence-panel {
  display: grid;
  gap: 0.5rem;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.citation-chip {
  border: 1px solid rgba(118, 146, 196, 0.22);
  background: rgba(244, 248, 255, 0.96);
  color: #24436a;
  border-radius: 16px;
  padding: 0.5rem 0.72rem;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.citation-chip:hover {
  transform: translateY(-1px);
  border-color: rgba(61, 126, 240, 0.28);
  background: rgba(255, 255, 255, 0.98);
}

.citation-chip small {
  color: var(--text-muted);
}

.empty-text {
  margin: 0;
  font-size: 0.84rem;
  color: var(--text-muted);
}
</style>
