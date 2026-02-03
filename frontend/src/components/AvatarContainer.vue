<template>
  <section class="avatar-card glass-panel depth-medium" aria-label="数字人控制面板">
    <header class="avatar-head">
      <div>
        <p class="avatar-eyebrow">Avatar Bridge</p>
        <h2>数字人联动</h2>
      </div>
      <span class="avatar-status" :class="state.ready ? 'online' : 'idle'">
        {{ state.ready ? "Unity Ready" : "Waiting Unity" }}
      </span>
    </header>

    <p class="avatar-subtitle">{{ subtitlePreview }}</p>

    <div class="emotion-row">
      <button v-for="emotion in emotions" :key="emotion" type="button" class="chip" @click="applyEmotion(emotion)">
        {{ emotion }}
      </button>
    </div>

    <div class="control-row">
      <span class="play-tag">{{ state.isPlaying ? "播报中" : "待机中" }}</span>
      <button type="button" class="stop-btn" @click="stopAvatar">停止</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import {
  avatarState,
  bindAvatarCallbacks,
  setAvatarEmotion,
  setAvatarGesture,
  stopAvatar,
  type AvatarEmotion,
} from "../services/avatarBridge";

const emotions: AvatarEmotion[] = ["calm", "supportive", "serious", "warning"];
const state = avatarState;

const subtitlePreview = computed(() => {
  if (!state.subtitle) {
    return "等待文本与音频输入。";
  }
  return state.subtitle.length > 52 ? `${state.subtitle.slice(0, 52)}...` : state.subtitle;
});

function applyEmotion(emotion: AvatarEmotion): void {
  setAvatarEmotion(emotion);
  const gesture = emotion === "warning" || emotion === "serious" ? "point" : "confirm";
  setAvatarGesture(gesture);
}

onMounted(() => {
  bindAvatarCallbacks();
});
</script>

<style scoped>
.avatar-card {
  border-radius: 20px;
  padding: 0.72rem;
  display: grid;
  gap: 0.52rem;
}

.avatar-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.6rem;
}

.avatar-eyebrow {
  margin: 0;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.avatar-head h2 {
  margin: 0.06rem 0 0;
  font-size: 0.98rem;
}

.avatar-status {
  border-radius: 999px;
  border: 1px solid transparent;
  padding: 0.2rem 0.54rem;
  font-size: 0.7rem;
  font-weight: 600;
  white-space: nowrap;
}

.avatar-status.online {
  background: rgba(85, 181, 134, 0.2);
  border-color: rgba(85, 181, 134, 0.5);
  color: #1c6d43;
}

.avatar-status.idle {
  background: rgba(255, 255, 255, 0.38);
  border-color: rgba(255, 255, 255, 0.25);
  color: var(--text-muted);
}

.avatar-subtitle {
  margin: 0;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(255, 255, 255, 0.34);
  padding: 0.42rem 0.52rem;
  min-height: 2.4rem;
  font-size: 0.8rem;
  color: var(--text-primary);
}

.emotion-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.34rem;
}

.chip {
  border: 1px solid rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.42);
  color: var(--accent-strong);
  border-radius: 999px;
  padding: 0.22rem 0.56rem;
  font-size: 0.74rem;
  cursor: pointer;
}

.control-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
}

.play-tag {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.stop-btn {
  border: 0;
  border-radius: 10px;
  padding: 0.32rem 0.64rem;
  background: rgba(226, 107, 106, 0.2);
  color: #922e2a;
  cursor: pointer;
}
</style>
