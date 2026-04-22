# Sprint 验收用例清单（可重复执行）

执行脚本：

```bash
backend/.venv/Scripts/python backend/scripts/run_sprint_acceptance.py --sprint all
```

可选按 Sprint 执行：

```bash
backend/.venv/Scripts/python backend/scripts/run_sprint_acceptance.py --sprint sprint1
backend/.venv/Scripts/python backend/scripts/run_sprint_acceptance.py --sprint sprint2
backend/.venv/Scripts/python backend/scripts/run_sprint_acceptance.py --sprint sprint3
```

## Sprint 1（知识库构建 + 向量检索接口）

1. 检索接口返回结构化 chunk（包含 chunk_id/law_name/article_no）。
2. chunk 详情接口可返回原文 text（供前端 EvidenceCard 展示）。
3. chunk 不存在时返回 404。
4. 检索参数越界（top_k > 20）触发校验错误。

## Sprint 2（RAG 问答闭环 + 结构化 JSON + 引用卡片）

1. `/api/chat` 返回结构化 answer_json（包含 conclusion/analysis/actions/citations）。
2. 无证据时触发“拒答守卫”（serious + 空 citations）。
3. 引用不在检索结果中时触发过滤/拒答。
4. 聊天服务异常时 API 返回稳定 500 文案。
5. 运行时配置接口可保存并立即影响聊天参数（如 Top K、citation 守卫）。

## Sprint 3（剧情法庭模拟）

1. `/api/case/catalog` 返回可选案件列表。
2. `peng_yu_case` 等案件可从 `opening` 推进并持久化会话。
3. 连续多轮推进后可进入 `verdict` 阶段。
4. “查看真实判决结果”分支可返回真实裁判结论，用于法律科普讲解。
