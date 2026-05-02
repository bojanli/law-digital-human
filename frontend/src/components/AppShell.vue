<template>
  <div class="app-shell">
    <main class="page-slot" :class="pageClass">
      <RouterView v-slot="{ Component, route: pageRoute }">
        <Transition name="panel-switch" mode="out-in">
          <component :is="Component" :key="pageRoute.path" />
        </Transition>
      </RouterView>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { RouterView, useRoute } from "vue-router";

const route = useRoute();
const pageClass = computed(() => (route.path.startsWith("/settings") ? "narrow" : "wide"));
</script>

<style scoped>
.app-shell {
  height: 100vh;
  overflow: hidden;
  padding: 1rem;
}

.page-slot {
  width: 100%;
  height: 100%;
  margin: 0 auto;
}

.page-slot.narrow {
  max-width: 1120px;
}

.page-slot.wide {
  max-width: 100%;
}

.panel-switch-enter-active,
.panel-switch-leave-active {
  transition: opacity 0.24s ease, transform 0.24s ease;
}

.panel-switch-enter-from,
.panel-switch-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 900px) {
  .app-shell {
    padding: 0.75rem;
  }
}
</style>
