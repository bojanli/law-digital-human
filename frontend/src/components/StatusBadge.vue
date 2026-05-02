<template>
  <div class="status-badge" :class="[`tone-${tone}`]">
    <span class="status-dot" />
    <span class="status-label">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string;
    tone?: "neutral" | "success" | "warning" | "danger" | "info";
  }>(),
  {
    tone: "neutral",
  },
);
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-height: 34px;
  padding: 0.45rem 0.8rem;
  border-radius: 999px;
  border: 1px solid rgba(133, 154, 181, 0.18);
  background: rgba(255, 255, 255, 0.78);
  color: var(--text-secondary);
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.6);
}

.tone-success {
  color: #1f8f67;
  background: rgba(227, 248, 239, 0.95);
}

.tone-warning {
  color: #a56a11;
  background: rgba(255, 243, 219, 0.96);
}

.tone-danger {
  color: #b64751;
  background: rgba(253, 236, 238, 0.96);
}

.tone-info {
  color: #396fd8;
  background: rgba(235, 242, 255, 0.96);
}
</style>
