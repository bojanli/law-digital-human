from fastapi import APIRouter
from app.schemas.chat import ChatRequest, ChatResponse, AnswerJson, Citation

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    # 先返回 mock，保证前端联调与 Unity 播报链路可跑通
    answer = AnswerJson(
        conclusion="（Mock）已收到你的问题，后续将接入RAG+LLM生成。",
        analysis=[
            f"session_id={req.session_id}",
            f"mode={req.mode}",
            "当前为后端骨架阶段：尚未接入检索与大模型。",
        ],
        actions=["你可以继续提问，或切换到案件模拟模式。"],
        citations=[
            Citation(
                chunk_id="mock_chunk_001",
                law_name="民法典（示例）",
                article_no="第X条（示例）",
                source="mock",
            )
        ],
        assumptions=["默认你希望获得普法性质的解释，而非律师执业意见。"],
        follow_up_questions=["你所在地区是哪里？（后续用于法律适用差异提醒）"],
        emotion="calm",
    )
    return ChatResponse(answer_json=answer, audio_url=None)
