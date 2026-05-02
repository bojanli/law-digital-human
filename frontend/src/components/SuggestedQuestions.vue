<template>
  <div v-if="questions.length" class="suggested-questions">
    <button v-for="question in questions" :key="question" type="button" class="question-chip" @click="$emit('select', question)">
      {{ question }}
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  questions: string[];
}>();

defineEmits<{
  select: [question: string];
}>();
</script>

<style scoped>
.suggested-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.question-chip {
  border: 1px solid rgba(119, 146, 194, 0.18);
  background: rgba(247, 250, 255, 0.95);
  color: var(--accent-strong);
  border-radius: 999px;
  padding: 0.62rem 0.9rem;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.question-chip:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 20px rgba(31, 57, 113, 0.1);
}
</style>
