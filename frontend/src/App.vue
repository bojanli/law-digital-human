<script setup lang="ts">
import HelloWorld from './components/HelloWorld.vue'
</script>

<template>
  <el-container style="min-height:100vh;">
    <el-aside width="220px">
      <el-menu router default-active="/chat">
        <el-menu-item index="/chat">法律问答</el-menu-item>
        <el-menu-item index="/case">案件模拟</el-menu-item>
        <el-menu-item index="/settings">设置</el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header style="display:flex; align-items:center; font-weight:600;">
        面向大学生普法教育的数字人智能问答交互系统
      </el-header>

      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>


<style scoped>
.logo {
  height: 6em;
  padding: 1.5em;
  will-change: filter;
  transition: filter 300ms;
}
.logo:hover {
  filter: drop-shadow(0 0 2em #646cffaa);
}
.logo.vue:hover {
  filter: drop-shadow(0 0 2em #42b883aa);
}
</style>
