<template>
  <header class="chat-header glass-panel depth-soft">
    <div class="title-wrap">
      <button type="button" class="sidebar-trigger" @click="$emit('toggleSidebar')">会话</button>
      <div>
        <p class="eyebrow">Digital Law Persona</p>
        <h2>{{ title }}</h2>
      </div>
    </div>

    <div class="status-row">
      <StatusBadge label="Backend Online" :tone="backendOnline ? 'success' : 'danger'" />
      <StatusBadge :label="asrLabel" :tone="asrTone" />
      <StatusBadge :label="ttsLabel" :tone="ttsTone" />
      <StatusBadge :label="avatarLabel" :tone="avatarTone" />
      <button type="button" class="avatar-toggle" @click="$emit('toggleSpeechControls')">
        {{ speechControlsExpanded ? "收起语音高级参数" : "展开语音高级参数" }}
      </button>
      <button type="button" class="avatar-toggle" @click="$emit('toggleAvatar')">
        {{ avatarCollapsed ? "展开数字人" : "收起数字人" }}
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from "vue";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{
  title: string;
  backendOnline: boolean;
  isRecording: boolean;
  isTranscribing: boolean;
  isSpeaking: boolean;
  avatarConnected: boolean;
  avatarCollapsed: boolean;
  speechControlsExpanded: boolean;
}>();

defineEmits<{
  toggleAvatar: [];
  toggleSidebar: [];
  toggleSpeechControls: [];
}>();

const asrLabel = computed(() => {
  if (props.isRecording) return "ASR 正在聆听";
  if (props.isTranscribing) return "ASR 转写中";
  return "ASR Standby";
});

const asrTone = computed(() => {
  if (props.isRecording) return "info";
  if (props.isTranscribing) return "warning";
  return "neutral";
});

const ttsLabel = computed(() => (props.isSpeaking ? "TTS 播报中" : "TTS Standby"));
const ttsTone = computed(() => (props.isSpeaking ? "info" : "neutral"));
const avatarLabel = computed(() => (props.avatarConnected ? "Avatar Connected" : "Avatar Offline"));
const avatarTone = computed(() => (props.avatarConnected ? "success" : "warning"));
</script>

<style scoped>
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.15rem;
  border-radius: 28px;
}

.title-wrap {
  display: flex;
  align-items: center;
  gap: 0.9rem;
}

.eyebrow {
  margin: 0;
  font-size: 0.72rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.title-wrap h2 {
  margin: 0.2rem 0 0;
  font-size: 1.2rem;
}

.status-row {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.42rem;
  max-width: 100%;
  overflow-x: auto;
}

.avatar-toggle,
.sidebar-trigger {
  border: 0;
  border-radius: 999px;
  padding: 0.5rem 0.72rem;
  background: rgba(242, 247, 255, 0.96);
  color: var(--accent-strong);
  font-weight: 600;
  font-size: 0.76rem;
  line-height: 1;
  cursor: pointer;
  white-space: nowrap;
}

.status-row :deep(.status-badge) {
  min-height: 30px;
  padding: 0.34rem 0.58rem;
  font-size: 0.72rem;
  gap: 0.34rem;
}

.sidebar-trigger {
  display: none;
}

@media (max-width: 900px) {
  .chat-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .status-row {
    justify-content: flex-start;
  }

  .sidebar-trigger {
    display: inline-flex;
  }
}
</style>
