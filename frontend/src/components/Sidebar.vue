<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="brand-block glass-panel depth-soft">
      <RouterLink to="/" class="home-btn">返回首页</RouterLink>
      <button type="button" class="sidebar-toggle mobile-only" @click="$emit('toggle')">
        {{ collapsed ? "展开" : "收起" }}
      </button>
    </div>

    <button type="button" class="new-session-btn" @click="$emit('newSession')">+ 新建对话</button>

    <section class="session-block glass-panel depth-soft">
      <header>
        <span>会话列表</span>
        <span class="session-count">{{ sessions.length }}</span>
      </header>
      <button
        v-for="session in sessions"
        :key="session.id"
        type="button"
        class="session-item"
        :class="{ active: session.id === activeSessionId }"
        @click="$emit('selectSession', session.id)"
      >
        <strong>{{ session.title }}</strong>
        <span>{{ session.updatedAt }}</span>
      </button>
      <p v-if="!sessions.length" class="empty-text">当前还没有会话。</p>
    </section>

  </aside>
</template>

<script setup lang="ts">
import { RouterLink } from "vue-router";

type SessionSummary = {
  id: string;
  title: string;
  updatedAt: string;
};

defineProps<{
  sessions: SessionSummary[];
  activeSessionId: string;
  collapsed: boolean;
}>();

defineEmits<{
  toggle: [];
  newSession: [];
  selectSession: [sessionId: string];
}>();

</script>

<style scoped>
.sidebar {
  width: 276px;
  min-width: 276px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.brand-block,
.session-block {
  border-radius: 24px;
  padding: 1rem;
}

.home-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  border-radius: 6px;
  padding: 0.12rem 0.45rem;
  background: rgba(237, 245, 255, 0.94);
  color: var(--accent-strong);
  text-decoration: none;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1;
}

.new-session-btn {
  border: 0;
  border-radius: 18px;
  background: linear-gradient(135deg, var(--accent), var(--accent-strong));
  color: #fff;
  padding: 0.82rem 1rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 18px 35px rgba(56, 92, 207, 0.24);
}

.session-block {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.session-block header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-secondary);
  font-weight: 600;
}

.session-count {
  border-radius: 999px;
  padding: 0.14rem 0.46rem;
  background: rgba(237, 244, 255, 0.92);
  color: var(--accent-strong);
  font-size: 0.74rem;
}

.session-item {
  border: 1px solid rgba(130, 154, 186, 0.14);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.58);
  padding: 0.85rem 0.95rem;
  text-align: left;
  cursor: pointer;
  display: grid;
  gap: 0.26rem;
  color: var(--text-secondary);
}

.session-item strong {
  font-size: 0.92rem;
  color: var(--text-primary);
}

.session-item span {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.session-item.active {
  border-color: rgba(84, 127, 228, 0.28);
  background: rgba(245, 248, 255, 0.96);
}

.empty-text {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.84rem;
}

.sidebar-toggle {
  margin-top: 0.8rem;
  border: 0;
  border-radius: 12px;
  background: rgba(237, 245, 255, 0.94);
  padding: 0.45rem 0.75rem;
  color: var(--accent-strong);
}

.mobile-only {
  display: none;
}

@media (max-width: 1080px) {
  .sidebar {
    width: 244px;
    min-width: 244px;
  }
}

@media (max-width: 900px) {
  .sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 50;
    width: min(82vw, 300px);
    min-width: 0;
    padding: 1rem;
    background: rgba(239, 245, 248, 0.92);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    transform: translateX(0);
    transition: transform 0.24s ease;
  }

  .sidebar.collapsed {
    transform: translateX(-100%);
  }

  .mobile-only {
    display: inline-flex;
  }
}
</style>
