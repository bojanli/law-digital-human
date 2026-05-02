<template>
  <div ref="windowRef" class="chat-window glass-panel depth-soft">
    <TransitionGroup name="message-slide" tag="div" class="message-list">
      <MessageBubble
        v-for="message in messages"
        :key="message.id"
        :role="message.role"
        :content="message.text"
        :citations="message.citations"
        :reasoning="message.reasoning"
        :suggestions="message.reasoning?.suggestions || []"
        @select-suggestion="$emit('selectSuggestion', $event)"
        @select-citation="$emit('selectCitation', $event)"
      />
      <slot name="extra-content" />
    </TransitionGroup>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import MessageBubble from "./MessageBubble.vue";
import type { ChatMessage, Citation } from "../types/chat";

const props = defineProps<{
  messages: ChatMessage[];
}>();

defineEmits<{
  selectSuggestion: [question: string];
  selectCitation: [citation: Citation];
}>();

const windowRef = ref<HTMLDivElement | null>(null);

watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    const node = windowRef.value;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  },
  { immediate: true },
);
</script>

<style scoped>
.chat-window {
  min-height: 0;
  height: 100%;
  border-radius: 28px;
  padding: 1rem 1rem 1.4rem;
  overflow-y: auto;
  overflow-x: hidden;
}

.message-list {
  display: grid;
  gap: 1rem;
}

.message-slide-enter-active,
.message-slide-leave-active {
  transition: all 0.24s ease;
}

.message-slide-enter-from,
.message-slide-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
