<template>
  <div class="app-shell">
    <nav class="nav-capsule glass-panel depth-medium" aria-label="主导航">
      <RouterLink
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: route.path.startsWith(item.path) }"
      >
        <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path :d="iconPath(item.icon)" />
        </svg>
        <span class="nav-label">{{ item.label }}</span>
      </RouterLink>
    </nav>

    <main class="page-slot">
      <RouterView v-slot="{ Component, route: pageRoute }">
        <Transition name="panel-switch" mode="out-in">
          <component :is="Component" :key="pageRoute.path" />
        </Transition>
      </RouterView>
    </main>
  </div>
</template>

<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from "vue-router";

type NavIcon = "chat" | "case" | "settings";

type NavItem = {
  path: string;
  label: string;
  icon: NavIcon;
};

const route = useRoute();

const navItems: NavItem[] = [
  { path: "/chat", label: "法律问答", icon: "chat" },
  { path: "/case", label: "案件模拟", icon: "case" },
  { path: "/settings", label: "系统设置", icon: "settings" },
];

function iconPath(icon: NavIcon): string {
  if (icon === "chat") {
    return "M4 5h16v10H8l-4 4V5Zm4 3h8v2H8V8Zm0 4h6v2H8v-2Z";
  }
  if (icon === "case") {
    return "M8 3h8l1 3h3v15H4V6h3l1-3Zm1.4 3h5.2l-.35-1H9.75L9.4 6ZM6 8v11h12V8H6Zm2 2h8v2H8v-2Zm0 4h5v2H8v-2Z";
  }
  return "M19.14 12.94a7.43 7.43 0 0 0 .05-.94 7.43 7.43 0 0 0-.05-.94l2.03-1.58-1.92-3.32-2.39.97a7.1 7.1 0 0 0-1.62-.94l-.36-2.54h-3.84l-.36 2.54c-.57.22-1.11.53-1.61.94l-2.4-.97-1.92 3.32 2.03 1.58a7.43 7.43 0 0 0-.05.94c0 .32.02.63.05.94L2.75 14.52l1.92 3.32 2.4-.97c.5.41 1.04.72 1.61.94l.36 2.54h3.84l.36-2.54c.57-.22 1.11-.53 1.62-.94l2.39.97 1.92-3.32-2.03-1.58ZM12 15.2A3.2 3.2 0 1 1 12 8.8a3.2 3.2 0 0 1 0 6.4Z";
}
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  width: 100%;
  padding: 1.5rem 1.5rem 1.5rem 8rem;
}

.page-slot {
  width: min(980px, 100%);
  margin-inline: auto;
}

.nav-capsule {
  position: fixed;
  left: 1.5rem;
  top: 50%;
  transform: translateY(-50%);
  width: 82px;
  border-radius: 999px;
  padding: 0.8rem 0.5rem;
  display: grid;
  gap: 0.6rem;
  z-index: 40;
}

.nav-item {
  border-radius: 999px;
  padding: 0.6rem 0.45rem;
  display: grid;
  justify-items: center;
  gap: 0.24rem;
  color: var(--text-muted);
  transition: all 0.22s ease;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.32);
  color: var(--accent-strong);
}

.nav-item.active {
  background: rgba(255, 255, 255, 0.52);
  color: var(--accent-strong);
  box-shadow: 0 8px 18px rgba(16, 40, 63, 0.15);
}

.nav-icon {
  width: 20px;
  height: 20px;
  fill: currentColor;
}

.nav-label {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.panel-switch-enter-active,
.panel-switch-leave-active {
  transition: opacity 0.28s ease, transform 0.28s ease;
}

.panel-switch-enter-from,
.panel-switch-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

@media (max-width: 900px) {
  .app-shell {
    padding: 1rem 1rem 6.2rem;
  }

  .nav-capsule {
    top: auto;
    left: 50%;
    bottom: 1.1rem;
    transform: translateX(-50%);
    width: auto;
    grid-auto-flow: column;
    grid-auto-columns: 84px;
    padding: 0.52rem;
  }
}
</style>
