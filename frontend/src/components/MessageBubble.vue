<template>
  <article class="message-row" :class="roleClass">
    <div class="avatar-marker">{{ marker }}</div>
    <div class="bubble" :class="roleClass">
      <p class="bubble-text">{{ content }}</p>

      <div v-if="role === 'assistant' && reasoning" class="reasoning-block glass-panel depth-soft">
        <details open>
          <summary>分析过程</summary>
          <div class="reasoning-grid">
            <section>
              <h4>事实提取</h4>
              <ul><li v-for="item in reasoning.facts" :key="`fact_${item}`">{{ item }}</li></ul>
            </section>
            <section>
              <h4>规则匹配</h4>
              <ul><li v-for="item in reasoning.rules" :key="`rule_${item}`">{{ item }}</li></ul>
            </section>
            <section>
              <h4>风险评估</h4>
              <ul><li v-for="item in reasoning.risks" :key="`risk_${item}`">{{ item }}</li></ul>
            </section></div>
        </details>
      </div>

      <EvidencePanel
        v-if="role === 'assistant'"
        :citations="citations"
        empty-text=""
        @select-citation="emit('selectCitation', $event)"
      />
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import EvidencePanel from "./EvidencePanel.vue";
import type { Citation, ChatRole, ReasoningSignature } from "../types/chat";

const props = withDefaults(
  defineProps<{
    role: ChatRole;
    content: string;
    citations?: Citation[];
    reasoning?: ReasoningSignature;
    suggestions?: string[];
  }>(),
  {
    citations: () => [],
    reasoning: undefined,
    suggestions: () => [],
  },
);

const emit = defineEmits<{
  selectSuggestion: [question: string];
  selectCitation: [citation: Citation];
}>();

const roleClass = computed(() => `role-${props.role}`);
const marker = computed(() => {
  if (props.role === "user") return "我";
  if (props.role === "system") return "系统";
  return "法";
});
</script>

<style scoped>
.message-row {
  display: flex;
  align-items: flex-end;
  gap: 0.9rem;
}

.role-user {
  justify-content: flex-end;
}

.avatar-marker {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: rgba(240, 246, 255, 0.96);
  color: var(--accent-strong);
  font-size: 0.8rem;
  font-weight: 700;
  flex: 0 0 auto;
}

.role-user .avatar-marker {
  order: 2;
  background: rgba(224, 240, 255, 1);
}

.bubble {
  max-width: min(760px, 88%);
  border-radius: 26px;
  padding: 1rem;
  display: grid;
  gap: 0.85rem;
  box-shadow: 0 18px 30px rgba(18, 41, 84, 0.08);
}

.bubble.role-assistant,
.bubble.role-system {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(129, 151, 181, 0.14);
}

.bubble.role-user {
  background: linear-gradient(135deg, rgba(228, 242, 255, 0.96), rgba(211, 234, 255, 0.98));
  border: 1px solid rgba(138, 181, 237, 0.2);
}

.bubble-text {
  margin: 0;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.72;
}

.reasoning-block {
  border-radius: 20px;
  padding: 0.8rem 0.9rem;
}

.reasoning-block summary {
  cursor: pointer;
  color: var(--accent-strong);
  font-weight: 600;
}

.reasoning-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
  margin-top: 0.8rem;
}

.reasoning-grid h4 {
  margin: 0 0 0.35rem;
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.reasoning-grid ul {
  margin: 0;
  padding-left: 1rem;
  color: var(--text-muted);
}

.reasoning-grid li + li {
  margin-top: 0.3rem;
}

@media (max-width: 900px) {
  .bubble {
    max-width: 100%;
  }

  .reasoning-grid {
    grid-template-columns: 1fr;
  }
}
</style>

