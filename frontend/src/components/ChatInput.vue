<template>
  <form class="chat-input glass-panel depth-medium" @submit.prevent="$emit('submit')">
    <div class="input-toolbar">
      <slot name="toolbar-left" />
      <button type="button" class="tool-btn" @click="$emit('clear')">清空</button>
      <button
        v-if="interruptVisible"
        type="button"
        class="tool-btn interrupt-btn"
        :disabled="interruptDisabled"
        @click="$emit('interrupt')"
      >
        {{ interruptLabel }}
      </button>
      <p v-if="listeningText" class="live-status">{{ listeningText }}</p>
    </div>

    <div class="input-row">
      <textarea
        :value="modelValue"
        class="composer-input"
        :placeholder="placeholder"
        :disabled="disabled"
        rows="1"
        @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
      />
      <button type="button" class="voice-btn" :disabled="voiceDisabled" @click="$emit('toggleVoice')">
        {{ voiceLabel }}
      </button>
      <button type="submit" class="send-btn" :disabled="sendDisabled">发送</button>
    </div>
  </form>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string;
  placeholder: string;
  disabled: boolean;
  sendDisabled: boolean;
  voiceDisabled: boolean;
  voiceLabel: string;
  listeningText: string;
  interruptVisible: boolean;
  interruptDisabled: boolean;
  interruptLabel: string;
}>();

defineEmits<{
  "update:modelValue": [value: string];
  submit: [];
  toggleVoice: [];
  clear: [];
  interrupt: [];
}>();
</script>

<style scoped>
.chat-input {
  position: sticky;
  bottom: 0;
  border-radius: 28px;
  padding: 0.9rem;
  display: grid;
  gap: 0.75rem;
}

.input-toolbar {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}

.tool-btn,
.voice-btn,
.send-btn {
  border: 0;
  cursor: pointer;
  font-weight: 600;
}

.tool-btn,
.voice-btn {
  border-radius: 999px;
  padding: 0.58rem 0.9rem;
  background: rgba(239, 246, 255, 0.94);
  color: var(--accent-strong);
}

.interrupt-btn {
  background: rgba(255, 237, 237, 0.96);
  color: #9f2a2a;
}

.input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 0.75rem;
  align-items: end;
}

.composer-input {
  min-height: 60px;
  max-height: 168px;
  resize: vertical;
  border: 0;
  outline: none;
  border-radius: 24px;
  padding: 1rem 1.1rem;
  background: rgba(255, 255, 255, 0.92);
  color: var(--text-primary);
}

.send-btn {
  border-radius: 18px;
  padding: 0.95rem 1.2rem;
  background: linear-gradient(135deg, var(--accent), var(--accent-strong));
  color: #fff;
  min-width: 92px;
}

.voice-btn:disabled,
.send-btn:disabled,
.tool-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.live-status {
  margin: 0 0 0 auto;
  color: var(--text-muted);
  font-size: 0.82rem;
}

@media (max-width: 720px) {
  .input-row {
    grid-template-columns: 1fr;
  }
}
</style>
