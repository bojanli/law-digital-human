<template>
  <section class="evidence-card glass-panel depth-soft">
    <header class="evidence-header">
      <p class="title">引用依据</p>
      <span class="count-chip">{{ citations.length }} 条</span>
    </header>

    <p v-if="!citations.length" class="empty-text">{{ emptyText }}</p>

    <div v-else class="chip-list">
      <button
        v-for="citation in citations"
        :key="citation.chunk_id"
        type="button"
        class="citation-chip"
        @click="openCitation(citation)"
      >
        <span class="law">{{ citation.law_name || "未标注法律名称" }}</span>
        <span class="article">{{ citation.article_no || "条号待补充" }}</span>
      </button>
    </div>

    <Transition name="pop-card">
      <aside v-if="activeCitation" class="citation-pop glass-panel depth-medium">
        <header class="pop-header">
          <p>法条依据</p>
          <div class="ops">
            <button type="button" class="op-btn" @click="copyChunkId(activeCitation.chunk_id)">复制ID</button>
            <button type="button" class="op-btn" @click="activeCitation = null">关闭</button>
          </div>
        </header>
        <p class="pop-law">{{ activeCitation.law_name || "未标注法律名称" }}</p>
        <p class="pop-article">{{ activeCitation.article_no || "条号待补充" }}</p>
        <p class="meta"><strong>source:</strong> {{ activeCitation.source || "未标注" }}</p>
        <p v-if="activeCitation.section" class="meta"><strong>section:</strong> {{ activeCitation.section }}</p>
        <p class="meta"><strong>chunk_id:</strong> {{ activeCitation.chunk_id }}</p>
        <div class="chunk-box">
          <p class="chunk-title">chunk 原文</p>
          <p v-if="chunkLoading" class="chunk-status">加载中...</p>
          <p v-else-if="chunkError" class="chunk-status error">{{ chunkError }}</p>
          <pre v-else class="chunk-text">{{ chunkText || "暂无内容" }}</pre>
        </div>
      </aside>
    </Transition>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";

type Citation = {
  chunk_id: string;
  law_name?: string | null;
  article_no?: string | null;
  section?: string | null;
  source?: string | null;
};

withDefaults(
  defineProps<{
    citations: Citation[];
    emptyText?: string;
  }>(),
  {
    emptyText: "当前回答未返回可核验引用依据。",
  },
);

const activeCitation = ref<Citation | null>(null);
const chunkText = ref("");
const chunkLoading = ref(false);
const chunkError = ref("");
const chunkCache = ref<Record<string, string>>({});

function openCitation(citation: Citation): void {
  activeCitation.value = citation;
  void loadChunkText(citation.chunk_id);
}

async function copyChunkId(chunkId: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(chunkId);
    ElMessage.success("已复制 chunk_id");
  } catch {
    ElMessage.error("复制失败（浏览器可能限制剪贴板权限）");
  }
}

async function loadChunkText(chunkId: string): Promise<void> {
  const cached = chunkCache.value[chunkId];
  if (cached) {
    chunkText.value = cached;
    chunkError.value = "";
    return;
  }

  chunkLoading.value = true;
  chunkError.value = "";
  chunkText.value = "";
  try {
    const res = await axios.get(`/api/knowledge/chunk/${encodeURIComponent(chunkId)}`);
    const text = typeof res.data?.text === "string" ? res.data.text.trim() : "";
    if (!text) {
      chunkError.value = "未返回法条原文。";
      return;
    }
    chunkCache.value[chunkId] = text;
    chunkText.value = text;
  } catch {
    chunkError.value = "chunk 原文加载失败，请稍后重试。";
  } finally {
    chunkLoading.value = false;
  }
}
</script>

<style scoped>
.evidence-card {
  border-radius: 16px;
  padding: 0.72rem;
}

.evidence-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  margin-bottom: 0.45rem;
}

.title {
  margin: 0;
  color: var(--accent-strong);
  font-size: 0.9rem;
  font-weight: 600;
}

.count-chip {
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.46);
  color: #1f6277;
  padding: 0.2rem 0.56rem;
  font-size: 0.74rem;
}

.empty-text {
  margin: 0;
  color: var(--text-muted);
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.42rem;
}

.citation-chip {
  border: 1px solid rgba(48, 112, 146, 0.25);
  background: rgba(255, 255, 255, 0.45);
  color: #174569;
  border-radius: 999px;
  padding: 0.25rem 0.62rem;
  cursor: pointer;
  display: flex;
  gap: 0.36rem;
}

.law {
  font-weight: 600;
}

.article {
  opacity: 0.82;
}

.citation-pop {
  position: fixed;
  right: 1.4rem;
  bottom: 1.4rem;
  width: min(320px, calc(100% - 2rem));
  border-radius: 18px;
  padding: 0.76rem;
  z-index: 70;
}

.pop-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.6rem;
}

.pop-header p {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.ops {
  display: flex;
  gap: 0.34rem;
}

.op-btn {
  border: 0;
  background: rgba(255, 255, 255, 0.46);
  color: var(--accent-strong);
  border-radius: 10px;
  padding: 0.3rem 0.55rem;
  cursor: pointer;
}

.pop-law {
  margin: 0.4rem 0 0;
  font-weight: 700;
}

.pop-article {
  margin: 0.18rem 0 0.42rem;
  color: #1f6277;
}

.meta {
  margin: 0.22rem 0 0;
  word-break: break-word;
  font-size: 0.82rem;
}

.chunk-box {
  margin-top: 0.56rem;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.24);
  background: rgba(255, 255, 255, 0.42);
  padding: 0.5rem;
}

.chunk-title {
  margin: 0 0 0.28rem;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.chunk-status {
  margin: 0;
  font-size: 0.8rem;
}

.chunk-status.error {
  color: #8f2e34;
}

.chunk-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 180px;
  overflow: auto;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 0.8rem;
  line-height: 1.45;
}

.pop-card-enter-active,
.pop-card-leave-active {
  transition: all 0.24s ease;
}

.pop-card-enter-from,
.pop-card-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.98);
}

@media (max-width: 920px) {
  .citation-pop {
    right: 1rem;
    left: 1rem;
    width: auto;
    bottom: 6.2rem;
  }
}
</style>
