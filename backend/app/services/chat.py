import json
from typing import Any
from urllib import error, request

from app.core.config import settings
from app.schemas.chat import AnswerJson, ChatRequest
from app.schemas.common import Citation


def build_answer(req: ChatRequest, evidence: list[dict[str, Any]]) -> AnswerJson:
    provider = settings.llm_provider.strip().lower()
    if provider in {"doubao", "ark"} and settings.ark_api_key and settings.ark_model:
        answer = _ask_ark(req, evidence)
        if answer is not None:
            return answer
    return _fallback_answer(req, evidence)


def _ask_ark(req: ChatRequest, evidence: list[dict[str, Any]]) -> AnswerJson | None:
    evidence_text = _render_evidence_text(evidence)
    prompt = (
        "你是高校普法助手。请基于证据回答，禁止编造法条。"
        "输出严格 JSON，字段："
        "conclusion, analysis, actions, assumptions, follow_up_questions, emotion, citation_chunk_ids。"
        "其中 analysis/actions/assumptions/follow_up_questions/citation_chunk_ids 都是数组。"
        "emotion 仅可选 calm/serious/supportive/warning。"
    )
    user_text = (
        f"用户问题：{req.text}\n"
        f"会话ID：{req.session_id}\n"
        f"模式：{req.mode}\n\n"
        f"可用证据（仅可引用这些 chunk_id）：\n{evidence_text}\n"
    )
    payload = {
        "model": settings.ark_model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    url = f"{settings.ark_base_url.rstrip('/')}/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req_obj = request.Request(
        url=url,
        data=data,
        headers={
            "Authorization": f"Bearer {settings.ark_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req_obj, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError:
        return None
    except error.URLError:
        return None
    except TimeoutError:
        return None

    try:
        raw = json.loads(body)
        content = raw["choices"][0]["message"]["content"]
        parsed = _parse_json_content(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
    return _answer_from_parsed(parsed, evidence)


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    return json.loads(text)


def _answer_from_parsed(parsed: dict[str, Any], evidence: list[dict[str, Any]]) -> AnswerJson:
    chunk_ids = parsed.get("citation_chunk_ids") or []
    chunk_ids = [str(x) for x in chunk_ids if isinstance(x, (str, int))]
    citations = _pick_citations_by_ids(evidence, chunk_ids)
    if not citations:
        citations = _to_citations(evidence[:3])
    emotion = str(parsed.get("emotion") or "calm").strip().lower()
    if emotion not in {"calm", "serious", "supportive", "warning"}:
        emotion = "calm"
    return AnswerJson(
        conclusion=str(parsed.get("conclusion") or "抱歉，我暂时无法给出稳定结论。"),
        analysis=_to_str_list(parsed.get("analysis")),
        actions=_to_str_list(parsed.get("actions")),
        assumptions=_to_str_list(parsed.get("assumptions")),
        follow_up_questions=_to_str_list(parsed.get("follow_up_questions")),
        citations=citations,
        emotion=emotion,
    )


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
            )
        )
    return citations


def _render_evidence_text(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "无"
    lines: list[str] = []
    for i, item in enumerate(evidence[:8], start=1):
        lines.append(
            f"{i}. chunk_id={item.get('chunk_id')} | 法律={item.get('law_name')} | "
            f"条号={item.get('article_no')} | 内容={str(item.get('text', ''))[:220]}"
        )
    return "\n".join(lines)


def _fallback_answer(req: ChatRequest, evidence: list[dict[str, Any]]) -> AnswerJson:
    citations = _to_citations(evidence[:3])
    no_evidence = "当前未检索到直接依据，建议补充事实后再问。"
    return AnswerJson(
        conclusion="我已收到你的问题，当前先返回检索增强的基础回答。",
        analysis=[
            f"session_id={req.session_id}",
            f"mode={req.mode}",
            no_evidence if not citations else "已从知识库检索到相关法条，可作为参考依据。",
        ],
        actions=[
            "补充关键事实（时间、地点、证据材料）可以提高回答准确度。",
            "如需严谨法律意见，请咨询执业律师。",
        ],
        assumptions=["默认你需要的是普法解释，而非律师执业意见。"],
        follow_up_questions=["请问事件发生在什么地区？是否有合同或聊天记录？"],
        citations=citations,
        emotion="calm",
    )
