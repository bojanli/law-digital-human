import re
import uuid
from typing import Any

from app.core.config import settings
from app.schemas.case import CaseResponse, CaseStartRequest, CaseStepRequest
from app.schemas.common import Citation
from app.services import knowledge as knowledge_service
from app.services import session_store

SUPPORTED_CASE_ID = "rent_deposit_dispute"
FACT_SLOTS = ["lease_exists", "deposit_amount", "damage", "handover_done", "evidence_types"]
REQUIRED_FACT_SLOTS = ["lease_exists", "damage", "handover_done"]

class CaseError(Exception):
    pass


class CaseNotFoundError(CaseError):
    pass


class CaseSessionNotFoundError(CaseError):
    pass


def start_case(req: CaseStartRequest) -> CaseResponse:
    if req.case_id != SUPPORTED_CASE_ID:
        raise CaseNotFoundError(f"不支持的案件模板: {req.case_id}")

    session_id = (req.session_id or "").strip() or f"case_{uuid.uuid4().hex[:12]}"
    state = {
        "session_id": session_id,
        "case_id": req.case_id,
        "state": "fact_confirm",
        "slots": {k: None for k in FACT_SLOTS},
        "path": [],
    }
    state["slots"]["evidence_types"] = []
    session_store.save_session(session_id, req.case_id, state)
    return _build_fact_confirm_response(state, opening=True)


def step_case(req: CaseStepRequest) -> CaseResponse:
    state = session_store.get_session(req.session_id)
    if not state:
        raise CaseSessionNotFoundError(f"会话不存在: {req.session_id}")
    _normalize_state(state)

    user_text = (req.user_input or "").strip()
    user_choice = (req.user_choice or "").strip()
    merged_text = user_text or user_choice

    current_state = state["state"]
    if current_state == "fact_confirm":
        _apply_fact_slots(state, merged_text)
        return _build_fact_confirm_response(state, opening=False)
    if current_state == "dispute_identify":
        return _handle_dispute_identify(state, user_text, user_choice)
    if current_state == "option_select":
        return _handle_option_select(state, user_text, user_choice)
    if current_state == "consequence_feedback":
        state["state"] = "completed"
        return _build_response(
            state=state,
            text="本轮案件模拟已完成。你可以继续补充细节，我会按同一案件继续分析。",
            next_question="是否要补充新的证据（合同、聊天记录、转账截图）以细化结论？",
            next_actions=["补充证据", "重新选择方案", "结束案件模拟"],
            emotion="supportive",
            citations=[],
        )
    return _build_response(
        state=state,
        text="当前案件会话已结束，请重新开始案件模拟。",
        next_question=None,
        next_actions=[],
        emotion="calm",
        citations=[],
    )


def _apply_fact_slots(state: dict[str, Any], text: str) -> None:
    slots = state["slots"]
    lease = _extract_bool(text, positive=["有合同", "签了合同", "签合同", "书面合同"], negative=["没合同", "未签合同", "没有合同"])
    damage = _extract_bool(text, positive=["有损坏", "损坏", "破坏"], negative=["无损坏", "没有损坏", "未损坏", "完好"])
    handover = _extract_bool(text, positive=["已搬走", "已经搬走", "已退租", "已交接", "交房"], negative=["没搬走", "未搬走", "未退租", "未交接"])
    deposit_amount = _extract_amount(text)
    evidence_types = _extract_evidence_types(text)

    if lease is not None:
        slots["lease_exists"] = lease
    if damage is not None:
        slots["damage"] = damage
    if handover is not None:
        slots["handover_done"] = handover
    if deposit_amount:
        slots["deposit_amount"] = deposit_amount
    if evidence_types:
        current = set(slots.get("evidence_types") or [])
        current.update(evidence_types)
        slots["evidence_types"] = sorted(current)


def _normalize_state(state: dict[str, Any]) -> None:
    state.setdefault("session_id", "")
    state.setdefault("case_id", SUPPORTED_CASE_ID)
    state.setdefault("state", "fact_confirm")
    state.setdefault("slots", {})
    state.setdefault("path", [])

    slots = state["slots"]
    for key in FACT_SLOTS:
        slots.setdefault(key, None)
    if slots["evidence_types"] is None:
        slots["evidence_types"] = []


def _build_fact_confirm_response(state: dict[str, Any], opening: bool) -> CaseResponse:
    missing = _missing_required_slots(state["slots"])
    if missing:
        question = _slot_question(missing[0])
        prefix = "已进入案件模拟。先补齐关键事实。" if opening else "收到，我先确认关键事实。"
        return _build_response(
            state=state,
            text=f"{prefix} 当前仍缺少：{', '.join(missing)}。",
            next_question=question,
            next_actions=[],
            emotion="serious",
            citations=[],
        )

    state["state"] = "dispute_identify"
    citations = _search_case_citations(state, stage="dispute_identify")
    return _build_response(
        state=state,
        text="事实已基本确认：你可以开始说明争议焦点（是否无故扣押金、是否存在维修争议）。",
        next_question="请选择争议类型：无故扣押金 / 维修扣费争议 / 合同条款争议",
        next_actions=["withhold_deposit", "repair_deduction", "contract_clause"],
        emotion="calm",
        citations=citations,
    )


def _handle_dispute_identify(state: dict[str, Any], user_text: str, user_choice: str) -> CaseResponse:
    dispute = user_choice or _infer_dispute_choice(user_text)
    if dispute not in {"withhold_deposit", "repair_deduction", "contract_clause"}:
        return _build_response(
            state=state,
            text="我还无法确认争议类型，请从预设选项中选一个。",
            next_question="请选择：withhold_deposit / repair_deduction / contract_clause",
            next_actions=["withhold_deposit", "repair_deduction", "contract_clause"],
            emotion="serious",
            citations=[],
        )

    state["state"] = "option_select"
    state["slots"]["dispute_type"] = dispute
    state["path"].append(f"dispute:{dispute}")
    citations = _search_case_citations(state, stage="option_select")
    return _build_response(
        state=state,
        text="争议类型已记录。下一步请选择处理方案，我会给出法律后果和证据建议。",
        next_question="请选择方案：协商沟通 / 投诉调解 / 起诉维权",
        next_actions=["negotiate", "mediate", "litigate"],
        emotion="supportive",
        citations=citations,
    )


def _handle_option_select(state: dict[str, Any], user_text: str, user_choice: str) -> CaseResponse:
    action = user_choice or _infer_action_choice(user_text)
    if action not in {"negotiate", "mediate", "litigate"}:
        return _build_response(
            state=state,
            text="请先明确你要采用的处理方案。",
            next_question="可选：negotiate / mediate / litigate",
            next_actions=["negotiate", "mediate", "litigate"],
            emotion="serious",
            citations=[],
        )

    state["state"] = "consequence_feedback"
    state["slots"]["selected_action"] = action
    state["path"].append(f"action:{action}")
    citations = _search_case_citations(state, stage="consequence_feedback")
    feedback = _build_consequence_feedback(state, has_evidence=bool(citations))
    next_question = "是否继续：补充证据、切换方案，或结束本次模拟？"
    next_actions = ["补充证据", "切换方案", "结束"]
    if not citations:
        next_question = "当前缺少直接依据，请补充合同、交接记录、催告记录后再选择方案。"
        next_actions = ["补充合同", "补充交接证据", "补充催告记录"]
    return _build_response(
        state=state,
        text=feedback,
        next_question=next_question,
        next_actions=next_actions,
        emotion="supportive",
        citations=citations,
    )


def _build_consequence_feedback(state: dict[str, Any], has_evidence: bool) -> str:
    action = state["slots"].get("selected_action")
    has_damage = bool(state["slots"].get("damage"))
    has_handover = bool(state["slots"].get("handover_done"))
    if not has_evidence:
        return "当前检索不到可直接支撑结论的法条依据。为避免误导，先不输出确定结论，请补充关键证据后继续。"

    if action == "negotiate":
        return "优先协商通常成本最低。建议先发出书面催告，要求房东在合理期限内说明扣款依据并退还剩余押金。"
    if action == "mediate":
        return "可向住建/街道调解或消费者组织投诉。若交接完成且无损坏，通常更有利于主张押金返还。"
    if action == "litigate":
        if has_handover and not has_damage:
            return "若已完成交接且房屋无损坏，起诉主张返还押金的胜算通常较高，关键在证据完整性。"
        return "起诉前建议补强证据（交接记录、损坏照片、修缮报价），否则争议事实不清会影响结果。"
    return "建议先明确争议与证据，再选择处理路径。"


def _missing_required_slots(slots: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in REQUIRED_FACT_SLOTS:
        if slots.get(key) is None:
            missing.append(key)
    return missing


def _slot_question(slot: str) -> str:
    prompts = {
        "lease_exists": "你和房东之间是否有书面或可证明的租赁约定？",
        "damage": "退租时房屋是否存在损坏，是否有交接记录？",
        "handover_done": "你是否已经搬离并完成交接？",
    }
    return prompts.get(slot, "请补充该事实。")


def _extract_bool(text: str, positive: list[str], negative: list[str]) -> bool | None:
    lowered = text.lower()
    if any(k in lowered for k in negative):
        return False
    if any(k in lowered for k in positive):
        return True
    return None


def _extract_amount(text: str) -> str | None:
    m = re.search(r"(\d{2,6})(?:\s*)元", text)
    if m:
        return f"{m.group(1)}元"
    return None


def _extract_evidence_types(text: str) -> list[str]:
    mapping = {
        "contract": ["合同", "租赁协议"],
        "chat_record": ["聊天记录", "微信记录", "短信"],
        "transfer_record": ["转账", "支付记录", "收据", "发票"],
        "handover_record": ["交接", "验房", "交房"],
        "photo_video": ["照片", "视频", "录音"],
    }
    found: list[str] = []
    for label, keys in mapping.items():
        if any(k in text for k in keys):
            found.append(label)
    return found


def _infer_dispute_choice(user_text: str) -> str | None:
    text = user_text.lower()
    if "无故" in text or "不退押金" in text or "扣押金" in text:
        return "withhold_deposit"
    if "维修" in text or "修缮" in text or "损坏" in text:
        return "repair_deduction"
    if "条款" in text or "合同" in text:
        return "contract_clause"
    return None


def _infer_action_choice(user_text: str) -> str | None:
    text = user_text.lower()
    if "协商" in text:
        return "negotiate"
    if "投诉" in text or "调解" in text:
        return "mediate"
    if "起诉" in text or "法院" in text:
        return "litigate"
    return None


def _build_stage_query(state: dict[str, Any], stage: str) -> str:
    slots = state.get("slots") or {}
    dispute = slots.get("dispute_type") or "押金争议"
    action = slots.get("selected_action") or "维权路径"
    lease = slots.get("lease_exists")
    handover = slots.get("handover_done")
    damage = slots.get("damage")
    evidence_types = ",".join(slots.get("evidence_types") or [])
    if stage == "dispute_identify":
        return f"租房 押金 退还 争议 责任 民法典 租赁合同 lease={lease} handover={handover} damage={damage}"
    if stage == "option_select":
        return f"租房 押金 {dispute} 协商 投诉 起诉 维权 路径 证据"
    return f"租房 押金 {dispute} {action} 证据责任 法律后果 evidence={evidence_types}"


def _search_case_citations(state: dict[str, Any], stage: str) -> list[Citation]:
    query = _build_stage_query(state, stage=stage)
    results = knowledge_service.search(query, settings.chat_top_k)
    citations: list[Citation] = []
    seen: set[str] = set()
    for item in results[:3]:
        chunk_id = item.get("chunk_id")
        if not chunk_id:
            continue
        chunk_id = str(chunk_id)
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        citations.append(
            Citation(
                chunk_id=chunk_id,
                law_name=item.get("law_name"),
                article_no=item.get("article_no"),
                section=item.get("section"),
                source=item.get("source"),
            )
        )
    return citations


def _build_response(
    state: dict[str, Any],
    text: str,
    next_question: str | None,
    next_actions: list[str],
    emotion: str,
    citations: list[Citation],
) -> CaseResponse:
    session_store.save_session(state["session_id"], state["case_id"], state)
    return CaseResponse(
        session_id=state["session_id"],
        case_id=state["case_id"],
        text=text,
        next_question=next_question,
        state=state["state"],
        slots=state["slots"],
        path=state["path"],
        missing_slots=_missing_required_slots(state["slots"]),
        next_actions=next_actions,
        citations=citations,
        emotion=emotion,
        audio_url=None,
    )
