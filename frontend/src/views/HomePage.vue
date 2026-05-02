<template>
  <div class="home-page">
    <section class="home-shell glass-panel depth-medium">
      <header class="hero">
        <p class="eyebrow">Law Digital Human</p>
        <h1>功能导航</h1>
        <p>选择你要进入的模块。</p>
      </header>

      <div class="cards">
        <RouterLink to="/chat" class="entry-card">
          <h2>法律问答</h2>
          <p>检索法条与案例，给出可核验建议。</p>
        </RouterLink>
        <RouterLink to="/case" class="entry-card">
          <h2>案件模拟</h2>
          <p>沉浸式模拟法庭审理流程。</p>
        </RouterLink>
        <RouterLink to="/settings" class="entry-card">
          <h2>系统设置</h2>
          <p>调整检索、守卫与运行参数。</p>
        </RouterLink>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts"></script>

<style scoped>
.home-page {
  height: 100%;
  display: grid;
  place-items: center;
  padding: 1rem;
}

.home-shell {
  width: min(980px, 100%);
  border-radius: 30px;
  padding: 1.2rem;
  display: grid;
  gap: 1rem;
}

.hero h1 {
  margin: 0.2rem 0 0.4rem;
}

.hero p {
  margin: 0;
  color: var(--text-secondary);
}

.eyebrow {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.8rem;
}

.entry-card {
  border-radius: 20px;
  padding: 1rem;
  text-decoration: none;
  border: 1px solid rgba(125, 151, 194, 0.2);
  background: rgba(255, 255, 255, 0.72);
  color: var(--text-primary);
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.entry-card:hover {
  transform: translateY(-2px);
  border-color: rgba(78, 120, 223, 0.35);
  box-shadow: 0 14px 24px rgba(30, 56, 110, 0.1);
}

.entry-card h2 {
  margin: 0 0 0.35rem;
  font-size: 1.08rem;
}

.entry-card p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.55;
}

@media (max-width: 900px) {
  .cards {
    grid-template-columns: 1fr;
  }
}
</style>
