import re
import uuid
from typing import Any

from app.core.config import settings
from app.schemas.case import CaseResponse, CaseStartRequest, CaseStepRequest
from app.schemas.common import Citation
from app.services import knowledge as knowledge_service
from app.services import session_store

CASE_TEMPLATES: dict[str, dict[str, Any]] = {
    "rent_deposit_dispute": {
        "fact_slots": ["lease_exists", "deposit_amount", "damage", "handover_done", "evidence_types"],
        "required_fact_slots": ["lease_exists", "damage", "handover_done"],
        "slot_questions": {
            "lease_exists": "你和房东之间是否有书面或可证明的租赁约定？",
            "damage": "退租时房屋是否存在损坏，是否有交接记录？",
            "handover_done": "你是否已经搬离并完成交接？",
        },
        "fact_intro_opening": "已进入案件模拟。先补齐关键事实。",
        "fact_intro_followup": "收到，我先确认关键事实。",
        "dispute_question": "请选择争议类型：无故扣押金 / 维修扣费争议 / 合同条款争议",
        "dispute_actions": ["withhold_deposit", "repair_deduction", "contract_clause"],
        "option_question": "请选择方案：协商沟通 / 投诉调解 / 起诉维权",
        "option_actions": ["negotiate", "mediate", "litigate"],
        "completion_question": "是否要补充新的证据（合同、聊天记录、转账截图）以细化结论？",
        "completion_actions": ["补充证据", "重新选择方案", "结束案件模拟"],
        "no_evidence_question": "当前缺少直接依据，请补充合同、交接记录、催告记录后再选择方案。",
        "no_evidence_actions": ["补充合同", "补充交接证据", "补充催告记录"],
    },
    "labor_wage_arrears": {
        "fact_slots": ["employment_exists", "wage_due_amount", "overtime_dispute", "payment_overdue", "evidence_types"],
        "required_fact_slots": ["employment_exists", "overtime_dispute", "payment_overdue"],
        "slot_questions": {
            "employment_exists": "你与用人单位是否存在劳动关系（合同/录用通知/考勤）？",
            "overtime_dispute": "是否存在加班费争议或未按约支付加班工资？",
            "payment_overdue": "工资是否已经逾期未发，是否超过约定发薪日？",
        },
        "fact_intro_opening": "已进入劳动争议模拟。先补齐关键事实。",
        "fact_intro_followup": "收到，我先核对劳动关系和欠薪事实。",
        "dispute_question": "请选择争议类型：拖欠工资 / 加班费争议 / 违法扣薪",
        "dispute_actions": ["arrears_wage", "overtime_pay", "illegal_deduction"],
        "option_question": "请选择方案：协商沟通 / 劳动监察投诉 / 劳动仲裁",
        "option_actions": ["negotiate", "complaint", "arbitration"],
        "completion_question": "是否继续：补充证据、切换方案，或结束本次模拟？",
        "completion_actions": ["补充证据", "切换方案", "结束案件模拟"],
        "no_evidence_question": "当前缺少直接依据，请补充劳动合同、考勤记录、工资流水后再选择方案。",
        "no_evidence_actions": ["补充劳动合同", "补充考勤记录", "补充工资流水"],
    },
}

DEFAULT_CASE_ID = "rent_deposit_dispute"


class CaseError(Exception):
    pass


class CaseNotFoundError(CaseError):
    pass


class CaseSessionNotFoundError(CaseError):
    pass


def start_case(req: CaseStartRequest) -> CaseResponse:
    template = _get_template(req.case_id)

    session_id = (req.session_id or "").strip() or f"case_{uuid.uuid4().hex[:12]}"
    state = {
        "session_id": session_id,
        "case_id": req.case_id,
        "state": "fact_confirm",
        "slots": {k: None for k in template["fact_slots"]},
        "path": [],
    }
    state["slots"]["evidence_types"] = []
    session_store.save_session(session_id, req.case_id, state)
    return _build_fact_confirm_response(state, opening=True)


def step_case(req: CaseStepRequest) -> CaseResponse:
    state = session_store.get_session(req.session_id)
    if not state:
        raise CaseSessionNotFoundError(f"会话不存在: {req.session_id}")
    template = _normalize_state(state)

    user_text = (req.user_input or "").strip()
    user_choice = (req.user_choice or "").strip()
    merged_text = user_text or user_choice

    current_state = state["state"]
    if current_state == "fact_confirm":
        _apply_fact_slots(state, template["case_id"], merged_text)
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
            next_question=template["completion_question"],
            next_actions=template["completion_actions"],
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


def _get_template(case_id: str) -> dict[str, Any]:
    template = CASE_TEMPLATES.get(case_id)
    if not template:
        raise CaseNotFoundError(f"不支持的案件模板: {case_id}")
    return {"case_id": case_id, **template}


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    case_id = str(state.get("case_id") or DEFAULT_CASE_ID)
    template = _get_template(case_id)

    state.setdefault("session_id", "")
    state.setdefault("case_id", template["case_id"])
    state.setdefault("state", "fact_confirm")
    state.setdefault("slots", {})
    state.setdefault("path", [])

    slots = state["slots"]
    for key in template["fact_slots"]:
        slots.setdefault(key, None)
    if slots["evidence_types"] is None:
        slots["evidence_types"] = []
    return template


def _apply_fact_slots(state: dict[str, Any], case_id: str, text: str) -> None:
    slots = state["slots"]
    if case_id == "labor_wage_arrears":
        employment = _extract_bool(
            text,
            positive=["有劳动合同", "存在劳动关系", "入职", "录用", "打卡"],
            negative=["没有劳动关系", "没签劳动合同", "未入职"],
        )
        overtime = _extract_bool(
            text,
            positive=["有加班", "加班费", "超时工作", "周末加班"],
            negative=["无加班", "没有加班", "不涉及加班"],
        )
        overdue = _extract_bool(
            text,
            positive=["拖欠工资", "未发工资", "逾期发薪", "超过发薪日", "逾期未发", "工资逾期未发", "逾期未发工资", "工资已逾期"],
            negative=["已发工资", "没有拖欠", "按时发薪"],
        )
        amount = _extract_amount(text)
        evidence_types = _extract_evidence_types(
            text,
            mapping={
                "labor_contract": ["劳动合同", "录用通知", "聘用协议"],
                "attendance": ["考勤", "打卡", "排班", "工时记录"],
                "salary_statement": ["工资条", "工资流水", "银行流水", "转账记录"],
                "chat_record": ["聊天记录", "微信记录", "短信"],
                "audio_video": ["录音", "录像", "视频"],
            },
        )

        if employment is not None:
            slots["employment_exists"] = employment
        if overtime is not None:
            slots["overtime_dispute"] = overtime
        if overdue is not None:
            slots["payment_overdue"] = overdue
        if amount:
            slots["wage_due_amount"] = amount
        if evidence_types:
            current = set(slots.get("evidence_types") or [])
            current.update(evidence_types)
            slots["evidence_types"] = sorted(current)
        return

    lease = _extract_bool(text, positive=["有合同", "签了合同", "签合同", "书面合同"], negative=["没合同", "未签合同", "没有合同"])
    damage = _extract_bool(text, positive=["有损坏", "损坏", "破坏"], negative=["无损坏", "没有损坏", "未损坏", "完好"])
    handover = _extract_bool(text, positive=["已搬走", "已经搬走", "已退租", "已交接", "交房"], negative=["没搬走", "未搬走", "未退租", "未交接"])
    deposit_amount = _extract_amount(text)
    evidence_types = _extract_evidence_types(
        text,
        mapping={
            "contract": ["合同", "租赁协议"],
            "chat_record": ["聊天记录", "微信记录", "短信"],
            "transfer_record": ["转账", "支付记录", "收据", "发票"],
            "handover_record": ["交接", "验房", "交房"],
            "photo_video": ["照片", "视频", "录音"],
        },
    )

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


def _build_fact_confirm_response(state: dict[str, Any], opening: bool) -> CaseResponse:
    template = _get_template(state["case_id"])
    missing = _missing_required_slots(state["slots"], template)
    if missing:
        question = _slot_question(missing[0], template)
        prefix = template["fact_intro_opening"] if opening else template["fact_intro_followup"]
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
    if state["case_id"] == "labor_wage_arrears":
        text = "事实已基本确认：你可以开始说明劳动争议焦点（拖欠工资、加班费或违法扣薪）。"
    else:
        text = "事实已基本确认：你可以开始说明争议焦点（是否无故扣押金、是否存在维修争议）。"
    return _build_response(
        state=state,
        text=text,
        next_question=template["dispute_question"],
        next_actions=template["dispute_actions"],
        emotion="calm",
        citations=citations,
    )


def _handle_dispute_identify(state: dict[str, Any], user_text: str, user_choice: str) -> CaseResponse:
    template = _get_template(state["case_id"])
    dispute = user_choice or _infer_dispute_choice(state["case_id"], user_text)
    if dispute not in set(template["dispute_actions"]):
        return _build_response(
            state=state,
            text="我还无法确认争议类型，请从预设选项中选一个。",
            next_question=f"请选择：{' / '.join(template['dispute_actions'])}",
            next_actions=template["dispute_actions"],
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
        next_question=template["option_question"],
        next_actions=template["option_actions"],
        emotion="supportive",
        citations=citations,
    )


def _handle_option_select(state: dict[str, Any], user_text: str, user_choice: str) -> CaseResponse:
    template = _get_template(state["case_id"])
    action = user_choice or _infer_action_choice(state["case_id"], user_text)
    if action not in set(template["option_actions"]):
        return _build_response(
            state=state,
            text="请先明确你要采用的处理方案。",
            next_question=f"可选：{' / '.join(template['option_actions'])}",
            next_actions=template["option_actions"],
            emotion="serious",
            citations=[],
        )

    state["state"] = "consequence_feedback"
    state["slots"]["selected_action"] = action
    state["path"].append(f"action:{action}")
    citations = _search_case_citations(state, stage="consequence_feedback")
    feedback = _build_consequence_feedback(state, has_evidence=bool(citations))
    next_question = template["completion_question"]
    next_actions = template["completion_actions"]
    if not citations:
        next_question = template["no_evidence_question"]
        next_actions = template["no_evidence_actions"]
    return _build_response(
        state=state,
        text=feedback,
        next_question=next_question,
        next_actions=next_actions,
        emotion="supportive",
        citations=citations,
    )


def _build_consequence_feedback(state: dict[str, Any], has_evidence: bool) -> str:
    if not has_evidence:
        return "当前检索不到可直接支撑结论的法条依据。为避免误导，先不输出确定结论，请补充关键证据后继续。"

    action = state["slots"].get("selected_action")
    if state["case_id"] == "labor_wage_arrears":
        if action == "negotiate":
            return "建议先保留书面催告记录并与单位协商补发工资，明确支付期限和补发金额。"
        if action == "complaint":
            return "可向劳动监察部门投诉。若能提供考勤和工资流水，通常更利于推动单位限期改正。"
        if action == "arbitration":
            return "申请劳动仲裁前请补齐劳动关系和欠薪证据，仲裁请求应写明拖欠工资与加班费明细。"
        return "建议先明确争议焦点，再选择处理路径。"

    has_damage = bool(state["slots"].get("damage"))
    has_handover = bool(state["slots"].get("handover_done"))
    if action == "negotiate":
        return "优先协商通常成本最低。建议先发出书面催告，要求房东在合理期限内说明扣款依据并退还剩余押金。"
    if action == "mediate":
        return "可向住建/街道调解或消费者组织投诉。若交接完成且无损坏，通常更有利于主张押金返还。"
    if action == "litigate":
        if has_handover and not has_damage:
            return "若已完成交接且房屋无损坏，起诉主张返还押金的胜算通常较高，关键在证据完整性。"
        return "起诉前建议补强证据（交接记录、损坏照片、修缮报价），否则争议事实不清会影响结果。"
    return "建议先明确争议与证据，再选择处理路径。"


def _missing_required_slots(slots: dict[str, Any], template: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in template["required_fact_slots"]:
        if slots.get(key) is None:
            missing.append(key)
    return missing


def _slot_question(slot: str, template: dict[str, Any]) -> str:
    return template["slot_questions"].get(slot, "请补充该事实。")


def _extract_bool(text: str, positive: list[str], negative: list[str]) -> bool | None:
    lowered = text.lower()
    if any(k in lowered for k in negative):
        return False
    if any(k in lowered for k in positive):
        return True
    return None


def _extract_amount(text: str) -> str | None:
    m = re.search(r"(\d{2,7})(?:\s*)元", text)
    if m:
        return f"{m.group(1)}元"
    return None


def _extract_evidence_types(text: str, mapping: dict[str, list[str]]) -> list[str]:
    found: list[str] = []
    for label, keys in mapping.items():
        if any(k in text for k in keys):
            found.append(label)
    return found


def _infer_dispute_choice(case_id: str, user_text: str) -> str | None:
    text = user_text.lower()
    if case_id == "labor_wage_arrears":
        if "拖欠工资" in text or "欠薪" in text or "没发工资" in text:
            return "arrears_wage"
        if "加班费" in text or "加班" in text:
            return "overtime_pay"
        if "扣薪" in text or "罚款" in text or "克扣" in text:
            return "illegal_deduction"
        return None

    if "无故" in text or "不退押金" in text or "扣押金" in text:
        return "withhold_deposit"
    if "维修" in text or "修缮" in text or "损坏" in text:
        return "repair_deduction"
    if "条款" in text or "合同" in text:
        return "contract_clause"
    return None


def _infer_action_choice(case_id: str, user_text: str) -> str | None:
    text = user_text.lower()
    if "协商" in text:
        return "negotiate"
    if case_id == "labor_wage_arrears":
        if "监察" in text or "投诉" in text:
            return "complaint"
        if "仲裁" in text:
            return "arbitration"
        return None
    if "投诉" in text or "调解" in text:
        return "mediate"
    if "起诉" in text or "法院" in text:
        return "litigate"
    return None


def _build_stage_query(state: dict[str, Any], stage: str) -> str:
    slots = state.get("slots") or {}
    evidence_types = ",".join(slots.get("evidence_types") or [])
    if state["case_id"] == "labor_wage_arrears":
        dispute = slots.get("dispute_type") or "欠薪争议"
        action = slots.get("selected_action") or "维权路径"
        if stage == "dispute_identify":
            return (
                "劳动关系 拖欠工资 加班费 劳动合同法 工资支付条例 "
                f"employment={slots.get('employment_exists')} overdue={slots.get('payment_overdue')}"
            )
        if stage == "option_select":
            return f"劳动争议 {dispute} 协商 监察 投诉 仲裁 证据"
        return f"劳动争议 {dispute} {action} 法律后果 证据责任 evidence={evidence_types}"

    dispute = slots.get("dispute_type") or "押金争议"
    action = slots.get("selected_action") or "维权路径"
    lease = slots.get("lease_exists")
    handover = slots.get("handover_done")
    damage = slots.get("damage")
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
    template = _get_template(state["case_id"])
    session_store.save_session(state["session_id"], state["case_id"], state)
    return CaseResponse(
        session_id=state["session_id"],
        case_id=state["case_id"],
        text=text,
        next_question=next_question,
        state=state["state"],
        slots=state["slots"],
        path=state["path"],
        missing_slots=_missing_required_slots(state["slots"], template),
        next_actions=next_actions,
        citations=citations,
        emotion=emotion,
        audio_url=None,
    )
