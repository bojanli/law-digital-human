<template>
  <el-card shadow="never" class="evidence-card">
    <template #header>
      <div class="header">
        <span>引用依据</span>
        <el-tag v-if="citations.length" type="success">{{ citations.length }} 条</el-tag>
        <el-tag v-else type="info">无</el-tag>
      </div>
    </template>

    <el-collapse v-if="citations.length" accordion>
      <el-collapse-item
        v-for="(c, idx) in citations"
        :key="c.chunk_id + '_' + idx"
        :name="idx"
      >
        <template #title>
          <div class="title">
            <span class="law">{{ c.law_name || "未标注法律名称" }}</span>
            <el-tag size="small" type="warning" v-if="c.article_no">{{ c.article_no }}</el-tag>
          </div>
        </template>

        <el-descriptions :column="1" border>
          <el-descriptions-item label="chunk_id">
            <div class="row">
              <span class="mono">{{ c.chunk_id }}</span>
              <el-button size="small" text type="primary" @click="copy(c.chunk_id)">复制</el-button>
            </div>
          </el-descriptions-item>

          <el-descriptions-item label="来源">
            {{ c.source || "未标注" }}
          </el-descriptions-item>

          <el-descriptions-item label="提示">
            后续会在这里展示该 chunk 的原文片段（需要接入 /api/knowledge/chunk/:id 或 search 调试接口）。
          </el-descriptions-item>
        </el-descriptions>
      </el-collapse-item>
    </el-collapse>

    <el-empty v-else description="当前回答未返回引用依据（或后端尚未接入RAG）" />
  </el-card>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";

type Citation = {
  chunk_id: string;
  law_name?: string | null;
  article_no?: string | null;
  source?: string | null;
};

defineProps<{
  citations: Citation[];
}>();

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("已复制 chunk_id");
  } catch {
    ElMessage.error("复制失败（浏览器可能限制剪贴板权限）");
  }
}
</script>

<style scoped>
.evidence-card {
  margin-top: 16px;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title {
  display: flex;
  gap: 8px;
  align-items: center;
}
.law {
  font-weight: 600;
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
    "Courier New", monospace;
}
</style>
