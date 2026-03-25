import json
import logging
import re
from typing import Any
from urllib import error, request

from app.core.config import settings
from app.schemas.chat import AnswerJson, ChatRequest
from app.schemas.common import Citation

logger = logging.getLogger(__name__)


def build_answer(req: ChatRequest, evidence: list[dict[str, Any]], history: list[dict[str, str]] | None = None) -> AnswerJson:
    provider = settings.llm_provider.strip().lower()
    if provider in {"doubao", "ark"} and settings.resolved_llm_api_key() and settings.resolved_llm_model():
        answer = _ask_ark(req, evidence, history)
        if answer is not None:
            return answer
    return _fallback_answer(req, evidence)


def _ask_ark(req: ChatRequest, evidence: list[dict[str, Any]], history: list[dict[str, str]] | None = None) -> AnswerJson | None:
    evidence_text = _render_evidence_text(evidence)
    citations = _to_citations(evidence[:3])

    system_prompt = (
        "你是一个专业的高校法律普法 AI 助手，名叫「法律数字人」。你的职责是：\n"
        "1. 用通俗易懂的中文回答用户的法律相关问题\n"
        "2. 如果提供了相关法律证据，请引用它们来支持你的回答\n"
        "3. 如果用户的问题不是法律问题（比如打招呼、闲聊），请友好地回应并引导用户提出法律问题\n"
        "4. 回答要有温度，不要生硬\n"
        "5. 禁止编造不存在的法条。如果你不确定，请诚实说明\n"
        "6. 如果知识库没有相关法条也没关系，你可以基于你的法律知识进行解答，但要注明仅供参考\n\n"
        "请直接用自然的中文回复，不需要输出 JSON 格式。回答要简洁专业但有亲和力。"
    )

    if evidence_text != "无":
        system_prompt += f"\n\n以下是从知识库检索到的相关法律条文，你可以引用：\n{evidence_text}"

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
        with request.urlopen(req_obj, timeout=30) as resp:
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

    # 非 JSON 格式，直接将自然语言回复包装成 AnswerJson
    # 智能拆分回复内容
    conclusion, analysis, actions, follow_ups = _split_natural_response(content)

    return AnswerJson(
        conclusion=conclusion,
        analysis=analysis,
        actions=actions,
        assumptions=[],
        follow_up_questions=follow_ups,
        citations=citations,
        emotion="calm",
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


def _split_natural_response(content: str) -> tuple[list[str], list[str], list[str], list[str]]:
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
        emotion="calm",
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
        with request.urlopen(req_obj, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            raw = json.loads(body)
            rewritten = raw["choices"][0]["message"]["content"].strip()
            return rewritten if rewritten else current_query
    except Exception:
        return current_query
