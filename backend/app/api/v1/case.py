from fastapi import APIRouter
from app.schemas.case import CaseStartRequest, CaseStepRequest, CaseResponse

router = APIRouter(prefix="/api/case", tags=["case"])


@router.post("/start", response_model=CaseResponse)
def start_case(req: CaseStartRequest) -> CaseResponse:
    return CaseResponse(
        text=f"（Mock）已进入案件模拟：{req.case_id}",
        next_question="请先描述事件发生的时间、地点，以及你与对方的关系。",
        state="fact_confirm",
        emotion="serious",
        citations=[],
        audio_url=None,
    )


@router.post("/step", response_model=CaseResponse)
def case_step(req: CaseStepRequest) -> CaseResponse:
    user_text = req.user_input or f"用户选择={req.user_choice}"
    return CaseResponse(
        text=f"（Mock）收到：{user_text}",
        next_question="为了继续分析：是否有书面合同/聊天记录/转账凭证？",
        state="fact_confirm",
        emotion="supportive",
        citations=[],
        audio_url=None,
    )
