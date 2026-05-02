<template>
  <section class="avatar-panel glass-panel depth-medium" :class="{ collapsed }">
    <header class="avatar-header">
      <div>
        <p class="eyebrow">Avatar Stage</p>
        <h3>数字人形象</h3>
      </div>
      <StatusBadge :label="statusLabel" :tone="statusTone" />
    </header>

    <div v-show="!collapsed" class="avatar-stage">
      <slot />
    </div>

    <div class="voice-row">
      <span>{{ voiceLabel }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{
  avatarStatus: "idle" | "listening" | "thinking" | "speaking" | "disconnected";
  subtitle: string;
  connected: boolean;
  collapsed: boolean;
}>();

const statusLabel = computed(() => {
  if (props.avatarStatus === "listening") return "正在聆听";
  if (props.avatarStatus === "thinking") return "正在思考";
  if (props.avatarStatus === "speaking") return "正在播报";
  if (props.avatarStatus === "disconnected") return "未连接";
  return "待机中";
});

const statusTone = computed(() => {
  if (props.avatarStatus === "speaking" || props.avatarStatus === "listening") return "info";
  if (props.avatarStatus === "thinking") return "warning";
  if (props.avatarStatus === "disconnected") return "danger";
  return "success";
});

const voiceLabel = computed(() => (props.avatarStatus === "speaking" ? "数字人正在播报..." : "语音通道空闲"));
</script>

<style scoped>
.avatar-panel {
  width: 360px;
  min-width: 360px;
  border-radius: 30px;
  padding: 1rem;
  display: grid;
  gap: 0.9rem;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.84), rgba(244, 249, 255, 0.9)),
    radial-gradient(120% 100% at 50% 0%, rgba(95, 138, 240, 0.12), transparent 70%);
}

.avatar-panel.collapsed {
  width: 76px;
  min-width: 76px;
  overflow: hidden;
}

.avatar-panel.collapsed .voice-row,
.avatar-panel.collapsed .avatar-stage h2,
.avatar-panel.collapsed .avatar-stage p,
.avatar-panel.collapsed .eyebrow {
  display: none;
}

.avatar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.eyebrow {
  margin: 0;
  font-size: 0.72rem;
  color: var(--text-muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.avatar-header h3 {
  margin: 0.22rem 0 0;
  font-size: 1.05rem;
}

.avatar-header :deep(.status-badge) {
  min-height: 28px;
  padding: 0.3rem 0.56rem;
  font-size: 0.74rem;
  gap: 0.3rem;
}

.voice-row {
  margin: 0;
  color: var(--text-secondary);
}

.avatar-stage {
  min-height: 0;
  overflow: hidden;
  border-radius: 26px;
  background: linear-gradient(180deg, rgba(238, 245, 255, 0.84), rgba(229, 241, 237, 0.72));
  border: 1px solid rgba(140, 166, 199, 0.14);
  padding: 0.5rem;
}

.voice-row {
  display: block;
  font-size: 0.82rem;
}

@media (max-width: 1280px) {
  .avatar-panel {
    width: 320px;
    min-width: 320px;
  }
}

@media (max-width: 900px) {
  .avatar-panel {
    width: 100%;
    min-width: 0;
  }

  .avatar-panel.collapsed {
    width: 100%;
    min-width: 0;
  }
}
</style>
