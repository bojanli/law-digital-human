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

## Sprint 3（案件模拟 FSM）

1. `rent_deposit_dispute` 全流程推进到 `consequence_feedback`。
2. 新模板 `labor_wage_arrears` 全流程推进到 `consequence_feedback`。
3. FSM 状态可持久化（path/state 可从 sqlite 恢复）。
4. 无证据时返回补证引导动作（新模板下给出劳动证据补充项）。
