后端 RAG 闭环说明与接口示例

1  RAG 闭环流程（后端侧）
1. 入口 `/api/chat` 接收 `session_id` 与 `text`，从 `knowledge_service.search` 拉取 Top-K 证据。
2. 证据以 `chunk_id` 为主键，附带 `law_name/article_no/section/source` 等字段，用于可回溯引用。
3. LLM 输出强约束为 JSON，包含 `conclusion/analysis/actions/assumptions/follow_up_questions/emotion/citation_chunk_ids`。
4. 服务端执行“引用校验”：
5. 无证据检索或无有效引用，直接拒答并给出追问。
6. 引用不在检索结果中，过滤或拒答，保证可解释性。
7. 生成通过后返回 `answer_json`，可选调用 TTS 得到 `audio_url`。

2  接口示例

2.1  知识检索 `http://127.0.0.1:8000/api/knowledge/search`

请求
```
POST http://127.0.0.1:8000/api/knowledge/search
```
```json
{
  "query": "租房押金不退怎么办",
  "top_k": 5
}
```

响应
```json
{
  "results": [
    {
      "chunk_id": "LZ-2023-001-12",
      "text": "出租人无正当理由不得扣留押金……",
      "law_name": "民法典",
      "article_no": "第七百零四条",
      "section": "租赁合同",
      "tags": "租赁,押金",
      "source": null,
      "score": 0.7812
    }
  ]
}
```

2.2  读取单条证据 `http://127.0.0.1:8000/api/knowledge/chunk/{chunk_id}`

请求
```
GET http://127.0.0.1:8000/api/knowledge/chunk/LZ-2023-001-12
```

响应
```json
{
  "chunk_id": "LZ-2023-001-12",
  "text": "出租人无正当理由不得扣留押金……",
  "law_name": "民法典",
  "article_no": "第七百零四条",
  "section": "租赁合同",
  "tags": "租赁,押金",
  "source": null
}
```

2.3  普通问答 `http://127.0.0.1:8000/api/chat`

请求
```
POST http://127.0.0.1:8000/api/chat
```
```json
{
  "session_id": "s-2026-02-09-0001",
  "text": "押金被扣但合同未注明扣款原因怎么办？",
  "mode": "chat"
}
```

响应
```json
{
  "answer_json": {
    "conclusion": "如果出租人无正当理由扣留押金，可要求返还并保留证据。",
    "analysis": [
      "押金扣留需有合同约定或合法理由。",
      "若无约定或事实依据，可主张返还。"
    ],
    "actions": [
      "保留合同与付款凭证。",
      "协商不成可通过调解或司法途径维权。"
    ],
    "citations": [
      {
        "chunk_id": "LZ-2023-001-12",
        "law_name": "民法典",
        "article_no": "第七百零四条",
        "section": "租赁合同",
        "source": null
      }
    ],
    "assumptions": [
      "你与出租人存在有效租赁合同关系。"
    ],
    "follow_up_questions": [
      "合同中是否约定了扣款条款？"
    ],
    "emotion": "calm"
  },
  "audio_url": null
}
```

2.4  案件模拟启动 `http://127.0.0.1:8000/api/case/start`

请求
```
POST http://127.0.0.1:8000/api/case/start
```
```json
{
  "case_id": "rent_deposit_v1"
}
```

响应
```json
{
  "session_id": "case-2026-02-09-0001",
  "case_id": "rent_deposit_v1",
  "text": "请先说明租期起止时间与是否签订书面合同。",
  "next_question": null,
  "state": "fact_collect",
  "slots": {},
  "missing_slots": [
    "lease_term",
    "has_contract"
  ],
  "path": [],
  "next_actions": [],
  "citations": [],
  "emotion": "supportive",
  "audio_url": null
}
```

2.5  案件模拟推进 `http://127.0.0.1:8000/api/case/step`

请求
```
POST http://127.0.0.1:8000/api/case/step
```
```json
{
  "session_id": "case-2026-02-09-0001",
  "user_input": "租期一年，签了合同"
}
```

响应
```json
{
  "session_id": "case-2026-02-09-0001",
  "case_id": "rent_deposit_v1",
  "text": "押金金额是多少？是否有转账记录或收据？",
  "next_question": null,
  "state": "fact_collect",
  "slots": {
    "lease_term": "一年",
    "has_contract": "是"
  },
  "missing_slots": [
    "deposit_amount",
    "has_receipt"
  ],
  "path": [
    "fact_collect"
  ],
  "next_actions": [],
  "citations": [],
  "emotion": "calm",
  "audio_url": null
}
```

3  引用校验与拒答规则说明
1. 当检索结果为空时，服务端返回拒答响应并提示补充事实。
2. 当 `citations` 为空或不在检索结果中时，服务端拒答或过滤非法引用。
3. 前端 EvidenceCard 只展示 `citations` 中的证据，保证可回溯与可验证。
