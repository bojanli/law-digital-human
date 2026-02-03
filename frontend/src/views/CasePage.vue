<template>
  <el-card>
    <template #header>
      <div class="header">
        <span>案件模拟（FSM）</span>
        <el-tag v-if="sessionId" type="success">session: {{ sessionId }}</el-tag>
        <el-tag v-else type="info">未开始</el-tag>
      </div>
    </template>

    <el-form label-width="110px" @submit.prevent>
      <el-form-item label="案件模板">
        <el-select v-model="caseId" style="width: 320px">
          <el-option label="租房押金纠纷（rent_deposit_dispute）" value="rent_deposit_dispute" />
        </el-select>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="starting" @click="startCase">开始案件模拟</el-button>
      </el-form-item>
    </el-form>

    <el-divider />

    <el-alert
      v-if="!sessionId"
      title="请先点击“开始案件模拟”，再进行多轮推进。"
      type="info"
      :closable="false"
      show-icon
    />

    <div v-else class="case-body">
      <el-card shadow="never">
        <template #header>当前状态</template>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="state">{{ current?.state || "-" }}</el-descriptions-item>
          <el-descriptions-item label="next_question">
            {{ current?.next_question || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="missing_slots">
            {{ (current?.missing_slots || []).join(", ") || "无" }}
          </el-descriptions-item>
          <el-descriptions-item label="path">
            {{ (current?.path || []).join(" -> ") || "无" }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never">
        <template #header>操作</template>
        <div class="actions">
          <el-button
            v-for="action in current?.next_actions || []"
            :key="action"
            :loading="stepping"
            @click="stepByChoice(action)"
          >
            {{ action }}
          </el-button>
        </div>
        <div class="input-row">
          <el-input
            v-model="userInput"
            type="textarea"
            :rows="3"
            placeholder="或输入自然语言推进流程（例如：有合同，已搬走，房屋无损坏）"
          />
          <el-button type="primary" :loading="stepping" @click="stepByInput">发送输入</el-button>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>消息流</template>
        <el-timeline>
          <el-timeline-item
            v-for="(item, idx) in messages"
            :key="`${idx}_${item.state}`"
            :type="idx === messages.length - 1 ? 'primary' : 'info'"
            :timestamp="item.state"
          >
            <div class="msg">{{ item.text }}</div>
            <div v-if="item.next_question" class="question">下一问：{{ item.next_question }}</div>
          </el-timeline-item>
        </el-timeline>
      </el-card>

      <EvidenceCard :citations="current?.citations || []" />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";
import EvidenceCard from "../components/EvidenceCard.vue";

type Citation = {
  chunk_id: string;
  law_name?: string | null;
  article_no?: string | null;
  source?: string | null;
};

type CaseResponse = {
  session_id: string;
  case_id: string;
  text: string;
  next_question?: string | null;
  state?: string | null;
  slots: Record<string, unknown>;
  path: string[];
  missing_slots: string[];
  next_actions: string[];
  citations: Citation[];
  emotion: string;
  audio_url?: string | null;
};

const caseId = ref("rent_deposit_dispute");
const sessionId = ref("");
const userInput = ref("");
const starting = ref(false);
const stepping = ref(false);
const current = ref<CaseResponse | null>(null);
const messages = ref<CaseResponse[]>([]);

function pushMessage(resp: CaseResponse) {
  current.value = resp;
  messages.value.push(resp);
}

async function startCase() {
  starting.value = true;
  try {
    const res = await axios.post<CaseResponse>("/api/case/start", { case_id: caseId.value });
    sessionId.value = res.data.session_id;
    messages.value = [];
    pushMessage(res.data);
    ElMessage.success("案件模拟已开始");
  } catch (err: any) {
    const detail = err?.response?.data?.detail || "启动失败";
    ElMessage.error(String(detail));
  } finally {
    starting.value = false;
  }
}

async function stepByChoice(choice: string) {
  if (!sessionId.value) return;
  stepping.value = true;
  try {
    const res = await axios.post<CaseResponse>("/api/case/step", {
      session_id: sessionId.value,
      user_choice: choice,
    });
    pushMessage(res.data);
  } catch (err: any) {
    const detail = err?.response?.data?.detail || "推进失败";
    ElMessage.error(String(detail));
  } finally {
    stepping.value = false;
  }
}

async function stepByInput() {
  if (!sessionId.value) return;
  const text = userInput.value.trim();
  if (!text) {
    ElMessage.warning("请输入内容");
    return;
  }
  stepping.value = true;
  try {
    const res = await axios.post<CaseResponse>("/api/case/step", {
      session_id: sessionId.value,
      user_input: text,
    });
    userInput.value = "";
    pushMessage(res.data);
  } catch (err: any) {
    const detail = err?.response?.data?.detail || "推进失败";
    ElMessage.error(String(detail));
  } finally {
    stepping.value = false;
  }
}
</script>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.case-body {
  display: grid;
  gap: 16px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.input-row {
  display: grid;
  gap: 8px;
}
.msg {
  white-space: pre-wrap;
}
.question {
  margin-top: 6px;
  color: #606266;
}
</style>
