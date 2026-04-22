# 论文材料闭环清单（2026-03-26）

## 1. 课题定位与最终方案

项目名称：面向大学生法律科普的数字人智能问答交互系统。  
最终方案采用“三层架构 + 两条主线”：

- 感知交互层：Vue3 前端（`/chat`、`/case`、`/settings`）；
- 系统决策层：FastAPI（RAG 问答、剧情法庭、会话与指标）；
- 表现层：数字人消息协议与前端桥接（`Avatar.Play/SetEmotion/Stop`）。

两条主线：

- 主线A：法律问答（结构化 JSON 输出 + citation 校验 + 无证据拒答）；
- 主线B：剧情法庭（著名案例沉浸式审理推进 + 分支选择 + 真实判决讲解）。

## 2. 代码与接口落地证据

已落地的关键实现（用于论文“系统实现”章节引用）：

- 问答接口与守卫链路：`backend/app/api/v1/chat.py`
- 问答服务结构化输出与拒答逻辑：`backend/app/services/chat.py`
- 知识检索与chunk回溯：`backend/app/services/knowledge.py`
- 剧情法庭服务：`backend/app/services/case.py`
- 运行时配置接口：`backend/app/api/v1/runtime_config.py`
- 运行时配置持久化：`backend/app/services/runtime_config.py`
- 前端设置页（接入后端配置）：`frontend/src/views/SettingsPage.vue`
- 评测脚本：`backend/scripts/run_eval_suite.py`
- KPI导出脚本：`backend/scripts/export_paper_kpi.py`

## 3. 今日可复现实验结果（真实生成）

### 3.1 固定测试集自动评测

执行时间：`2026-03-26 21:37:33`  
来源文件：`backend/tests/reports/eval_suite_report.json`

核心结果：

- total: 20
- passed: 20
- failed: 0
- pass_rate: 1.0000
- chat_regular_pass_rate: 1.0000
- chat_incomplete_pass_rate: 1.0000
- case_branch_pass_rate: 1.0000
- chat_latency_p50_ms: 34.99
- chat_latency_p90_ms: 41.42
- case_latency_p50_ms: 328.35
- case_latency_p90_ms: 372.33

说明：该评测默认使用`mock`问答提供者（`use_live_provider=false`），用于保证论文中的可复现实验稳定性。

### 3.2 近30天KPI导出

执行时间：`2026-03-26`  
来源文件：`backend/tests/reports/paper_kpi.json`

核心结果：

- days: 30
- chat_total: 19
- chat_with_evidence: 16
- citation_hit_rate: 1.0000
- chat_no_evidence: 3
- no_evidence_reject_rate: 1.0000
- chat_latency_p50_ms: 2793.85
- chat_latency_p90_ms: 12441.64
- case_step_latency_p50_ms: 30.80
- case_step_latency_p90_ms: 17996.23

说明：该KPI基于实际运行期`metrics.db`，含真实网络环境波动，适合论文“系统在真实环境下的性能表现”章节。

## 4. 论文章节映射建议

- 第1章 研究背景与意义：强调“大学生常见法律场景 + 可解释AI普法”。
- 第2章 需求与总体架构：写三层架构、两条主线、边界与风险控制。
- 第3章 关键技术与实现：
  - RAG检索与引用回溯；
  - 结构化输出与守卫机制；
  - 剧情法庭多轮交互设计；
  - 运行时配置与可调参能力。
- 第4章 实验与评估：
  - 固定测试集自动评测（20/20）；
  - KPI指标（命中率、拒答率、延迟）；
  - 典型案例演示截图与流程说明。
- 第5章 总结与展望：
  - 已完成闭环；
  - 后续可做Unity表现层深化、混合检索增强、反馈闭环优化。

## 5. 答辩演示最小闭环（建议）

1. 启动后端与前端，展示`/settings`可实时配置（TopK、拒答、校验）。
2. 在`/chat`演示两类样例：
   - 证据充分：返回结构化结论 + citation；
   - 信息不足：触发拒答与追问。
3. 在`/case`演示剧情法庭推进至`verdict`，再触发“查看真实判决结果”。
4. 出示自动评测报告与KPI报告文件，证明可复现与量化结果。

## 6. 可复现命令（附录可直接引用）

```powershell
# 1) 单元/集成测试
backend\.venv\Scripts\python.exe -m pytest -q

# 2) 固定测试集自动评测（论文主实验）
backend\.venv\Scripts\python.exe backend\scripts\run_eval_suite.py

# 3) 导出近30天论文KPI
backend\.venv\Scripts\python.exe backend\scripts\export_paper_kpi.py --days 30
```

## 7. 当前遗留与后续优化（如实写入论文）

- Unity WebGL表现层尚未形成与仓库同级的一体化交付（当前重点在后端与前端闭环）。
- `run_eval_suite.py`目前使用`mock`模式保证复现，建议在附录增加一轮`--use-live-provider`实验对照。
- 若继续优化论文质量，可补“大学生用户访谈或小规模问卷”来增强应用价值论证。
