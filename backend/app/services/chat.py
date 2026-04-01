import json
import logging
import re
from typing import Any
from urllib import error, request

from app.core.config import settings
from app.schemas.chat import AnswerJson, ChatRequest
from app.schemas.common import Citation
from app.services.runtime_config import get_runtime_config

logger = logging.getLogger(__name__)


def build_answer(req: ChatRequest, evidence: list[dict[str, Any]], history: list[dict[str, str]] | None = None) -> AnswerJson:
    runtime = get_runtime_config()
    if runtime.reject_without_evidence and not evidence:
        return _reject_without_evidence(req)

    provider = settings.llm_provider.strip().lower()
    answer: AnswerJson | None = None
    if provider in {"doubao", "ark"} and settings.resolved_llm_api_key() and settings.resolved_llm_model():
        answer = _ask_ark(req, evidence, history)
    if answer is None:
        answer = _fallback_answer(req, evidence)
    return _finalize_answer(answer, evidence, runtime.default_emotion, runtime.strict_citation_check)


def _ask_ark(req: ChatRequest, evidence: list[dict[str, Any]], history: list[dict[str, str]] | None = None) -> AnswerJson | None:
    evidence_text = _render_evidence_text(evidence)

    system_prompt = (
        "你是一个专业的高校法律普法 AI 助手，名叫「法律数字人」。你的职责是：\n"
        "1. 用通俗易懂的中文回答用户的法律相关问题\n"
        "2. 如果提供了相关法律证据，请引用它们来支持你的回答\n"
        "3. 如果用户的问题不是法律问题（比如打招呼、闲聊），请友好地回应并引导用户提出法律问题\n"
        "4. 回答要有温度，不要生硬\n"
        "5. 禁止编造不存在的法条。如果你不确定，请诚实说明\n"
        "6. 必须输出严格 JSON，不要输出 markdown，不要输出解释。\n\n"
        "返回结构："
        '{"conclusion":"结论","analysis":["分析1"],"actions":["建议1"],'
        '"assumptions":["事实假设"],"follow_up_questions":["追问1"],'
        '"emotion":"calm","citation_chunk_ids":["chunk_id_1"]}'
    )

    if evidence_text != "无":
        system_prompt += (
            "\n\n以下是检索到的依据（包含法条与真实案例）：\n"
            "请优先使用法条给出规则，再引用案例做类比说明。\n"
            f"{evidence_text}"
        )

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history[-6:])  # 只保留最近 3 轮对话
    messages.append({"role": "user", "content": req.text})

    payload = {
        "model": settings.resolved_llm_model(),
        "messages": messages,
        "temperature": 0.5,
    }
    url = f"{settings.resolved_llm_base_url()}/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req_obj = request.Request(
        url=url,
        data=data,
        headers={
            "Authorization": f"Bearer {settings.resolved_llm_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req_obj, timeout=get_runtime_config().timeout_sec) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as e:
        logger.warning("LLM HTTPError: %s", e)
        return None
    except error.URLError as e:
        logger.warning("LLM URLError: %s", e)
        return None
    except TimeoutError:
        logger.warning("LLM timeout")
        return None

    try:
        raw = json.loads(body)
        content = raw["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        logger.warning("LLM response parse error: %s", e)
        return None

    # 尝试解析 JSON 格式（兼容模型可能返回 JSON 的情况）
    json_answer = _try_parse_json_answer(content, evidence)
    if json_answer is not None:
        return json_answer

    # 非 JSON 格式时，尽量把自然语言回复压回结构化 AnswerJson。
    conclusion, analysis, actions, follow_ups = _split_natural_response(content)

    return AnswerJson(
        conclusion=conclusion,
        analysis=analysis,
        actions=actions,
        assumptions=[],
        follow_up_questions=follow_ups,
        citations=[],
        emotion=get_runtime_config().default_emotion,
    )


def _try_parse_json_answer(content: str, evidence: list[dict[str, Any]]) -> AnswerJson | None:
    """尝试将 LLM 回复解析为 JSON 格式的 AnswerJson"""
    text = content.strip()
    # 尝试提取 JSON 块
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    elif not text.startswith("{"):
        return None

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if "conclusion" not in parsed:
        return None

    chunk_ids = parsed.get("citation_chunk_ids") or []
    chunk_ids = [str(x) for x in chunk_ids if isinstance(x, (str, int))]
    citations = _pick_citations_by_ids(evidence, chunk_ids)
    if not citations:
        citations = _to_citations(evidence[:3])

    emotion = str(parsed.get("emotion") or "calm").strip().lower()
    if emotion not in {"calm", "serious", "supportive", "warning"}:
        emotion = "calm"

    return AnswerJson(
        conclusion=str(parsed.get("conclusion") or ""),
        analysis=_to_str_list(parsed.get("analysis")),
        actions=_to_str_list(parsed.get("actions")),
        assumptions=_to_str_list(parsed.get("assumptions")),
        follow_up_questions=_to_str_list(parsed.get("follow_up_questions")),
        citations=citations,
        emotion=emotion,
    )


def _split_natural_response(content: str) -> tuple[str, list[str], list[str], list[str]]:
    """将自然语言回复智能拆分为 conclusion, analysis, actions, follow_ups"""
    lines = [line.strip() for line in content.split("\n") if line.strip()]

    # 简单回复直接作为 conclusion
    if len(lines) <= 3:
        return content.strip(), [], [], []

    # 长回复：第一段作为 conclusion，其余作为 analysis
    conclusion = lines[0]
    analysis = []
    actions = []
    follow_ups = []

    section = "analysis"
    for line in lines[1:]:
        lower = line.lower()
        if any(kw in lower for kw in ["建议", "可以", "应当", "需要", "步骤", "方案"]):
            section = "actions"
        if any(kw in lower for kw in ["？", "吗", "呢", "是否"]):
            follow_ups.append(line.lstrip("- ·•"))
            continue

        cleaned = line.lstrip("- ·•0123456789.、）)")
        if cleaned:
            if section == "actions":
                actions.append(cleaned)
            else:
                analysis.append(cleaned)

    return conclusion, analysis, actions, follow_ups


def _to_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _pick_citations_by_ids(evidence: list[dict[str, Any]], chunk_ids: list[str]) -> list[Citation]:
    evidence_map = {str(item.get("chunk_id")): item for item in evidence if item.get("chunk_id")}
    picked: list[Citation] = []
    for chunk_id in chunk_ids:
        item = evidence_map.get(chunk_id)
        if not item:
            continue
        picked.append(
            Citation(
                chunk_id=str(item.get("chunk_id")),
                law_name=item.get("law_name"),
                article_no=item.get("article_no"),
                section=item.get("section"),
                source=item.get("source"),
                source_type=item.get("source_type"),
                case_id=item.get("case_id"),
                case_name=item.get("case_name"),
            )
        )
    return picked


def _to_citations(evidence: list[dict[str, Any]]) -> list[Citation]:
    citations: list[Citation] = []
    for item in evidence:
        chunk_id = item.get("chunk_id")
        if not chunk_id:
            continue
        citations.append(
            Citation(
                chunk_id=str(chunk_id),
                law_name=item.get("law_name"),
                article_no=item.get("article_no"),
                section=item.get("section"),
                source=item.get("source"),
                source_type=item.get("source_type"),
                case_id=item.get("case_id"),
                case_name=item.get("case_name"),
            )
        )
    return citations


def _render_evidence_text(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "无"
    lines: list[str] = []
    for i, item in enumerate(evidence[:8], start=1):
        source_type = str(item.get("source_type") or "law")
        head = "法条" if source_type == "law" else "案例"
        name = item.get("law_name") if source_type == "law" else (item.get("case_name") or item.get("law_name"))
        index = item.get("article_no") if source_type == "law" else (item.get("case_id") or "案例")
        lines.append(
            f"{i}. 类型={head} | chunk_id={item.get('chunk_id')} | 名称={name} | "
            f"标识={index} | 内容={str(item.get('text', ''))[:220]}"
        )
    return "\n".join(lines)


def _fallback_answer(req: ChatRequest, evidence: list[dict[str, Any]]) -> AnswerJson:
    citations = _to_citations(evidence[:3])
    return AnswerJson(
        conclusion="抱歉，AI 助手暂时无法连接，请稍后再试。如果问题持续，请检查网络连接。",
        analysis=[
            "当前大模型服务未能响应，已返回离线提示。",
        ],
        actions=[
            "请稍后重试，或提供更具体的法律问题描述。",
            "如需严谨法律意见，请咨询执业律师。",
        ],
        assumptions=[],
        follow_up_questions=["请问你遇到了什么法律问题？"],
        citations=citations,
        emotion=get_runtime_config().default_emotion,
    )


def _reject_without_evidence(req: ChatRequest) -> AnswerJson:
    text = (req.text or "").strip()
    return AnswerJson(
        conclusion="当前未检索到可核验的法律依据，暂时无法给出确定结论。",
        analysis=[
            "为了避免编造法条或给出不稳妥建议，系统已停止直接作答。",
            "请先补充更具体的事实、证据或争议点，再继续分析。",
        ],
        actions=[
            "补充事件时间、地点、身份关系和关键证据。",
            "说明是否有合同、聊天记录、转账记录、截图或录音。",
        ],
        assumptions=[],
        follow_up_questions=_build_follow_up_questions(text),
        citations=[],
        emotion="serious",
    )


def _build_follow_up_questions(text: str) -> list[str]:
    hints: list[str] = []
    if any(keyword in text for keyword in ["押金", "租房", "房东", "租客"]):
        hints.extend(["是否签订书面租赁合同？", "押金金额和扣留理由是什么？"])
    if any(keyword in text for keyword in ["工资", "兼职", "劳动", "加班"]):
        hints.extend(["是否存在劳动合同或考勤记录？", "拖欠工资持续了多久？"])
    if any(keyword in text for keyword in ["网购", "退款", "假货", "平台"]):
        hints.extend(["是否保留订单截图和商家沟通记录？", "平台是否已经介入处理？"])
    if not hints:
        hints.extend(
            [
                "能否补充事件经过、关键时间点和争议焦点？",
                "你目前掌握了哪些合同、聊天记录、支付凭证或截图？",
            ]
        )
    return hints[:3]


def _finalize_answer(
    answer: AnswerJson,
    evidence: list[dict[str, Any]],
    default_emotion: str,
    strict_citation_check: bool,
) -> AnswerJson:
    evidence_chunk_ids = {str(item.get("chunk_id")) for item in evidence if item.get("chunk_id")}
    citations = answer.citations

    if strict_citation_check:
        citations = [citation for citation in answer.citations if citation.chunk_id in evidence_chunk_ids]
    elif not citations:
        citations = _to_citations(evidence[:3])

    emotion = (answer.emotion or default_emotion or "calm").strip().lower()
    if emotion not in {"calm", "serious", "supportive", "warning"}:
        emotion = default_emotion or "calm"

    if strict_citation_check and evidence and not citations:
        return AnswerJson(
            conclusion="当前回答未能生成可核验引用，系统已中止直接结论输出。",
            analysis=[
                "模型回复中缺少有效引用，无法证明结论来自已检索证据。",
                "为保证普法内容可靠性，本轮改为谨慎提示。",
            ],
            actions=[
                "请换一种问法，或补充更明确的事实描述。",
                "也可以先查看下方已命中的法条，再继续提问。",
            ],
            assumptions=[],
            follow_up_questions=answer.follow_up_questions or _build_follow_up_questions(answer.conclusion),
            citations=[],
            emotion="serious",
        )

    return AnswerJson(
        conclusion=answer.conclusion.strip() if answer.conclusion else "当前暂无法输出稳定结论，请补充事实后继续。",
        analysis=[item.strip() for item in answer.analysis if item.strip()],
        actions=[item.strip() for item in answer.actions if item.strip()],
        assumptions=[item.strip() for item in answer.assumptions if item.strip()],
        follow_up_questions=[item.strip() for item in answer.follow_up_questions if item.strip()],
        citations=citations,
        emotion=emotion,
    )


def rewrite_query(history: list[dict[str, str]], current_query: str) -> str:
    if not history:
        return current_query
    
    provider = settings.llm_provider.strip().lower()
    if provider not in {"doubao", "ark"} or not settings.resolved_llm_api_key():
        return current_query
        
    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[-4:]]) # 只看最近几轮防止超长
    prompt = (
        "你是查询意图重写助手。请根据以下历史对话，将最新的用户问题重写为一个独立、完整且没有代词的查询语句，用于去向量数据库检索法律条文。\n"
        "规则：除了重写后的查询语句外，不要输出任何其他解释性内容。如果不需要重写（本来就很完整），则原样输出。\n\n"
        f"【历史对话】\n{history_text}\n\n"
        f"【最新问题】\n{current_query}\n\n"
        "重写结果："
    )
    
    payload = {
        "model": settings.resolved_llm_model(),
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    url = f"{settings.resolved_llm_base_url()}/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req_obj = request.Request(
        url=url,
        data=data,
        headers={
            "Authorization": f"Bearer {settings.resolved_llm_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req_obj, timeout=get_runtime_config().timeout_sec) as resp:
            body = resp.read().decode("utf-8")
            raw = json.loads(body)
            rewritten = raw["choices"][0]["message"]["content"].strip()
            return rewritten if rewritten else current_query
    except Exception:
        return current_query
