<template>
  <el-card>
    <template #header>
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span>法律问答（RAG）- 联调测试</span>
        <el-tag type="success" v-if="healthOk">Backend OK</el-tag>
        <el-tag type="danger" v-else>Backend Down</el-tag>
      </div>
    </template>

    <el-form @submit.prevent>
      <el-form-item label="session_id">
        <el-input v-model="sessionId" />
      </el-form-item>

      <el-form-item label="问题">
        <el-input v-model="text" type="textarea" :rows="3" placeholder="输入任意内容，测试 /api/chat mock" />
      </el-form-item>

      <el-button type="primary" :loading="loading" @click="send">发送</el-button>
    </el-form>

    <el-divider />

    <el-card v-if="answer" shadow="never">
      <template #header>后端返回（answer_json）</template>
      <pre style="white-space:pre-wrap; word-break:break-word;">{{ answer }}</pre>
    </el-card>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import axios from "axios";

const sessionId = ref("demo_session_001");
const text = ref("我租房押金不退怎么办？");
const loading = ref(false);
const answer = ref<string>("");
const healthOk = ref(false);

async function checkHealth() {
  try {
    await axios.get("/health");
    healthOk.value = true;
  } catch {
    healthOk.value = false;
  }
}

async function send() {
  loading.value = true;
  try {
    const res = await axios.post("/api/chat", {
      session_id: sessionId.value,
      text: text.value,
      mode: "chat",
      case_state: null,
    });
    answer.value = JSON.stringify(res.data, null, 2);
  } finally {
    loading.value = false;
  }
}

onMounted(checkHealth);
</script>
