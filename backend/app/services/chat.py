import json
import logging
import re
from collections.abc import Iterator
from typing import Any
from urllib import error, request

from app.core.config import settings
from app.schemas.chat import AnswerJson, ChatRequest
from app.schemas.common import Citation
from app.services.runtime_config import get_runtime_config
from app.services import web_search as web_search_service

logger = logging.getLogger(__name__)
_REWRITE_HINTS = ("这", "那", "它", "他", "她", "其", "上述", "前面", "刚才", "之前", "这个", "那个")
_USER_REFERENTIAL_PATTERNS = (
    "没签合同",
    "不退呢",
    "怎么办呢",
    "可以吗",
    "合法么",
    "算违法吗",
    "这种情况",
    "这种行为",
)
_QUERY_SELF_CONTAINED_KEYWORDS = (
    "网购",
    "假货",
    "退款",
    "押金",
    "房东",
    "租房",
    "工资",
    "劳动",
    "加班",
    "合同",
    "侵权",
    "诈骗",
    "借款",
)
_ANSWER_EVIDENCE_LIMIT = 3
_ANSWER_HISTORY_LIMIT = 4
_STREAM_CITATION_SENTINEL = "[[CITATIONS:"
_OUT_OF_SCOPE_FOLLOW_UP = "请描述具体法律问题。"

_LEGAL_SIGNAL_KEYWORDS = (
    "法律",
    "法条",
    "法规",
    "违法",
    "合法吗",
    "合法么",
    "犯罪",
    "判刑",
    "处罚",
    "罚款",
    "赔偿",
    "维权",
    "起诉",
    "诉讼",
    "法院",
    "仲裁",
    "律师",
    "合同",
    "兼职",
    "协议",
    "纠纷",
    "责任",
    "权利",
    "义务",
    "证据",
    "报警",
    "劳动",
    "劳动仲裁",
    "工资",
    "工伤",
    "社保",
    "押金",
    "租房",
    "房东",
    "出租人",
    "承租人",
    "欠款",
    "欠钱",
    "借款",
    "借钱",
    "离婚",
    "继承",
    "侵权",
    "诈骗",
    "打人",
    "退款",
    "消费",
    "消费者",
    "扣押",
)
_FINANCE_MARKET_KEYWORDS = ("股票", "股价", "基金", "期货", "证券", "大盘", "行情", "币价", "虚拟币", "加密货币")
_INVESTMENT_PREDICTION_KEYWORDS = (
    "预测",
    "涨跌",
    "涨还是跌",
    "会涨",
    "会跌",
    "走势",
    "买入",
    "卖出",
    "推荐",
    "荐股",
    "收益",
    "投资建议",
)
_MEDICAL_KEYWORDS = ("看病", "症状", "吃什么药", "用药", "诊断", "治疗", "医院", "发烧", "咳嗽", "头痛", "医学")
_TECH_KEYWORDS = ("代码", "编程", "python", "java", "javascript", "bug", "报错", "数据库", "服务器", "接口", "算法")
_NEWS_KEYWORDS = ("新闻", "热搜", "最新消息", "天气", "气温", "明天天气", "今天发生")
_CASUAL_KEYWORDS = ("你好", "讲个笑话", "写首诗", "翻译", "你是谁", "闲聊", "聊天")
_NO_BASIS_MARKERS = (
    "无法根据依据",
    "依据中未涉及",
    "给定依据未涉及",
    "无法判断",
    "无法给出结论",
    "无法给出确定结论",
    "不能根据现有依据",
    "未检索到",
    "没有直接命中",
)
_LEGAL_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "labor": ("工资", "兼职", "劳动", "加班", "用人单位", "劳动合同", "拖欠", "辞退", "社保", "工伤", "劳动报酬"),
    "rent": (
        "租房",
        "房屋租赁",
        "租赁合同",
        "房东",
        "出租人",
        "租客",
        "承租人",
        "押金",
        "保证金",
        "担保",
        "租赁押金",
        "押金返还",
        "房租",
        "租赁",
        "出租",
        "退租",
        "不退",
        "到期不退",
        "返还争议",
        "扣押",
        "扣留",
        "拒绝返还",
    ),
    "consumer": ("网购", "假货", "退款", "退货", "消费者", "商家", "平台", "订单", "售后"),
    "loan": ("借款", "欠款", "还钱", "债务", "转账", "欠条", "借条", "利息"),
    "marriage": ("离婚", "抚养", "婚姻", "夫妻", "财产分割", "彩礼", "子女"),
    "traffic": ("交通事故", "车祸", "酒驾", "肇事", "交警", "赔偿", "保险"),
    "criminal": ("诈骗", "盗窃", "故意伤害", "刑法", "犯罪", "判刑", "拘留", "报警"),
    "investment_legal": ("内幕", "未公开信息", "证券", "操纵市场", "非法集资", "金融诈骗", "洗钱", "破坏金融管理秩序"),
}

_LEGAL_TOPIC_SYNONYMS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("房东",), ("出租人", "租赁合同", "房屋租赁")),
    (("租客",), ("承租人", "租赁合同", "房屋租赁")),
    (("租房",), ("房屋租赁", "租赁合同", "出租人", "承租人")),
    (("押金",), ("保证金", "担保", "租赁押金", "押金返还")),
    (("不退", "没退", "到期不退"), ("返还争议", "扣押", "扣留", "拒绝返还")),
)


def build_answer(req: ChatRequest, evidence: list[dict[str, Any]], history: list[dict[str, str]] | None = None) -> AnswerJson:
    runtime = get_runtime_config()
    if _is_out_of_scope_request(req.text):
        return _out_of_scope_answer(req)

    if not evidence:
        return _answer_without_local_evidence(req)

    provider = settings.llm_provider.strip().lower()
    answer: AnswerJson | None = None
    if provider in {"doubao", "ark"} and settings.resolved_llm_api_key() and settings.resolved_llm_model():
        answer = _ask_ark(req, evidence, history)
    if answer is None:
        answer = _fallback_answer(req, evidence)
    finalized = _finalize_answer(answer, evidence, runtime.default_emotion, _effective_citation_strict(req, runtime.strict_citation_check), req)
    if _looks_like_no_evidence_answer(finalized.conclusion):
        return _answer_without_local_evidence(req)
    return finalized


def expand_legal_query(query: str) -> str:
    text = (query or "").strip()
    if not text:
        return query

    if not _is_legal_domain_question(text):
        return text

    expansions: list[str] = [text]
    tags = _extract_legal_topic_tags(text)
    if "rent" in tags:
        expansions.extend(
            [
                "租赁合同 押金返还 出租人 承租人",
                "房东不退押金 租房押金 扣押押金 拒绝返还 民法典",
            ]
        )

    expanded = " ".join(dict.fromkeys(part.strip() for part in expansions if part.strip()))
    return expanded


def _ask_ark(req: ChatRequest, evidence: list[dict[str, Any]], history: list[dict[str, str]] | None = None) -> AnswerJson | None:
    messages = _build_answer_messages(req, evidence, history)
    runtime = get_runtime_config()
    content = _chat_completion_text(
        messages,
        model=_resolve_llm_model(req.model_variant),
        max_tokens=_effective_max_tokens(req, runtime.max_tokens),
        temperature=_effective_temperature(req, runtime.temperature),
    )
    if content is None:
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


def select_answer_evidence(evidence: list[dict[str, Any]], limit: int = _ANSWER_EVIDENCE_LIMIT) -> list[dict[str, Any]]:
    if not evidence or limit <= 0:
        return []

    laws = [dict(item) for item in evidence if str(item.get("source_type") or "law") == "law"]
    cases = [dict(item) for item in evidence if str(item.get("source_type") or "") == "case"]

    selected: list[dict[str, Any]] = []
    selected.extend(laws[:2])
    remaining = max(0, limit - len(selected))
    if remaining > 0:
        selected.extend(cases[:1 if cases else 0])
    remaining = max(0, limit - len(selected))
    if remaining > 0:
        fallback_pool = laws[2:] + cases[1:] + [dict(item) for item in evidence if item not in selected]
        selected.extend(fallback_pool[:remaining])

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in selected:
        chunk_id = str(item.get("chunk_id") or "")
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        deduped.append(_trim_evidence_item(item))
        if len(deduped) >= limit:
            break
    return deduped


def stream_answer_text(req: ChatRequest, evidence: list[dict[str, Any]], history: list[dict[str, str]] | None = None) -> Iterator[str]:
    messages = _build_stream_messages(req, evidence, history)
    runtime = get_runtime_config()
    yield from _chat_completion_stream(
        messages,
        model=_resolve_llm_model(req.model_variant),
        max_tokens=_effective_max_tokens(req, runtime.max_tokens),
        temperature=_effective_temperature(req, runtime.temperature),
    )


def build_answer_from_stream_text(content: str, evidence: list[dict[str, Any]]) -> AnswerJson:
    cleaned, chunk_ids = _extract_stream_citations(content)
    conclusion, analysis, actions, _ = _split_natural_response(cleaned)
    citations = _pick_citations_by_ids(evidence, chunk_ids)
    if not citations:
        citations = _to_citations(evidence[:2])
    return AnswerJson(
        conclusion=conclusion,
        analysis=analysis[:2],
        actions=actions[:2],
        assumptions=[],
        follow_up_questions=[],
        citations=citations,
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

    emotion = str(parsed.get("emotion") or "calm").strip().lower()
    if emotion not in {"calm", "serious", "supportive", "warning"}:
        emotion = "calm"

    return AnswerJson(
        conclusion=str(parsed.get("conclusion") or ""),
        analysis=_to_str_list(parsed.get("analysis"))[:2],
        actions=_to_str_list(parsed.get("actions"))[:2],
        assumptions=_to_str_list(parsed.get("assumptions")),
        follow_up_questions=_to_str_list(parsed.get("follow_up_questions")),
        citations=citations,
        emotion=emotion,
    )


def _split_natural_response(content: str) -> tuple[str, list[str], list[str], list[str]]:
    """将自然语言回复智能拆分为 conclusion, analysis, actions, follow_ups"""
    sanitized = _strip_citation_sentinel(content)
    lines = [line.strip() for line in sanitized.split("\n") if line.strip()]

    # 简单回复直接作为 conclusion
    if len(lines) <= 3:
        return sanitized.strip(), [], [], []

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

    return conclusion, analysis[:2], actions[:2], follow_ups[:2]


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
    for i, item in enumerate(evidence[:_ANSWER_EVIDENCE_LIMIT], start=1):
        source_type = str(item.get("source_type") or "law")
        head = "法条" if source_type == "law" else "案例"
        name = item.get("law_name") if source_type == "law" else (item.get("case_name") or item.get("law_name"))
        index = item.get("article_no") if source_type == "law" else (item.get("case_id") or "案例")
        content = str(item.get("text", "")).replace("\n", " ").strip()
        lines.append(
            f"{i}. 类型={head} | chunk_id={item.get('chunk_id')} | 名称={name} | "
            f"标识={index} | 内容={content[:120]}"
        )
    return "\n".join(lines)


def _fallback_answer(req: ChatRequest, evidence: list[dict[str, Any]]) -> AnswerJson:
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
        citations=[],
        emotion=get_runtime_config().default_emotion,
    )


def _answer_without_local_evidence(req: ChatRequest) -> AnswerJson:
    web_hits = web_search_service.search_public_web(f"{req.text} 法律", limit=4, timeout_sec=min(get_runtime_config().timeout_sec, 20))
    if web_hits:
        online = _ask_ark_with_web_results(req, web_hits)
        if online is not None:
            return online
        return _fallback_web_answer(req, web_hits)

    return _fallback_no_evidence_answer(req)


def _fallback_no_evidence_answer(req: ChatRequest) -> AnswerJson:
    text = (req.text or "").strip()
    if "rent" in _extract_legal_topic_tags(text):
        return _legal_domain_no_citation_answer(req)

    return AnswerJson(
        conclusion=(
            "当前本地知识库没有直接命中可核验依据，且公开网络检索暂不可用。"
            "以下仅为一般性普法提示，不构成正式法律意见，请结合事实自行核实。"
        ),
        analysis=[
            "缺少可核验来源时，不应把结论表述为确定法律判断。",
            "补充时间、金额、身份关系、合同、聊天记录、付款凭证等事实后，可重新检索本地知识库。",
        ],
        actions=[
            "补充事件时间、地点、身份关系和关键证据。",
            "说明是否有合同、聊天记录、转账记录、截图或录音。",
        ],
        assumptions=[],
        follow_up_questions=_build_follow_up_questions(text),
        citations=[],
        emotion="supportive",
    )


def _fallback_web_answer(req: ChatRequest, web_hits: list[web_search_service.WebSearchHit]) -> AnswerJson:
    bullets = [f"{idx + 1}. {hit.title}：{hit.snippet}" for idx, hit in enumerate(web_hits[:3]) if hit.title]
    return AnswerJson(
        conclusion="当前知识库没有直接命中这类问题，下面是我从公开网络信息中整理的参考方向，不能替代正式法律意见。",
        analysis=bullets[:2],
        actions=[
            "请结合你自己的证据、事实经过和当地规则自行判断。",
            "如涉及金额较大或争议复杂，建议咨询律师或向官方平台核实。",
        ],
        assumptions=[],
        follow_up_questions=_build_follow_up_questions(req.text),
        citations=[],
        emotion="supportive",
    )


def _ask_ark_with_web_results(req: ChatRequest, web_hits: list[web_search_service.WebSearchHit]) -> AnswerJson | None:
    provider = settings.llm_provider.strip().lower()
    if provider not in {"doubao", "ark"} or not settings.resolved_llm_api_key() or not settings.resolved_llm_model():
        return None

    web_text = "\n".join(
        f"{idx + 1}. 标题={hit.title} | 摘要={hit.snippet} | 链接={hit.url}"
        for idx, hit in enumerate(web_hits[:4])
    )
    prompt = (
        "你是高校法律普法助手。当前本地知识库没有直接命中用户问题。"
        "下面给你的是公开网络搜索摘要，请输出一个谨慎、非确定性的参考回答。"
        "不要把网络搜索内容说成本地知识库依据。"
        "必须明确提醒：以下内容来自公开网络信息整理，需用户自行判断并进一步核实。"
        '输出严格 JSON，不要 markdown。格式：{"conclusion":"一句话结论","analysis":["最多2条分析"],'
        '"actions":["最多2条建议"],"emotion":"supportive","follow_up_questions":["最多2条补充问题"]}\n'
        f"【用户问题】{req.text.strip()[:240]}\n"
        f"【公开网络摘要】\n{web_text}"
    )
    runtime = get_runtime_config()
    content = _chat_completion_text(
        [{"role": "user", "content": prompt}],
        model=_resolve_llm_model(req.model_variant),
        max_tokens=_effective_max_tokens(req, max(runtime.max_tokens, 320)),
        temperature=_effective_temperature(req, runtime.temperature),
    )
    if content is None:
        return None

    parsed = _try_parse_json_answer(content, [])
    if parsed is not None:
        parsed.citations = []
        parsed.emotion = "supportive"
        parsed.conclusion = _prefix_external_disclaimer(parsed.conclusion)
        return parsed

    conclusion, analysis, actions, follow_ups = _split_natural_response(content)
    return AnswerJson(
        conclusion=_prefix_external_disclaimer(conclusion),
        analysis=analysis[:2],
        actions=actions[:2] or [
            "请结合你自己的证据、事实经过和交易记录自行判断。",
            "如争议较大，建议向律师、平台客服或主管部门进一步核实。",
        ],
        assumptions=[],
        follow_up_questions=follow_ups[:2] or _build_follow_up_questions(req.text),
        citations=[],
        emotion="supportive",
    )


def _prefix_external_disclaimer(text: str) -> str:
    cleaned = (text or "").strip()
    notice = "以下内容根据公开网络信息整理，不属于本地知识库结论，仅供参考并需你自行判断核实。"
    if not cleaned:
        return notice
    if cleaned.startswith("以下内容根据公开网络信息整理"):
        return cleaned
    return f"{notice} {cleaned}"


def _build_follow_up_questions(text: str) -> list[str]:
    hints: list[str] = []
    if any(keyword in text for keyword in ["押金", "租房", "房东", "租客"]):
        hints.extend(
            [
                "是否签订书面租赁合同？",
                "押金金额是多少？",
                "房东不退押金的理由是什么？",
                "是否已经退租并完成房屋交接？",
            ]
        )
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
    return hints[:4]


def _is_out_of_scope_request(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False

    if _contains_legal_signal(normalized):
        return False

    if _is_investment_prediction_request(normalized):
        return True

    out_of_scope_groups = (_MEDICAL_KEYWORDS, _TECH_KEYWORDS, _NEWS_KEYWORDS, _CASUAL_KEYWORDS)
    return any(any(keyword in normalized for keyword in group) for group in out_of_scope_groups)


def _is_investment_prediction_request(text: str) -> bool:
    return any(keyword in text for keyword in _FINANCE_MARKET_KEYWORDS) and any(
        keyword in text for keyword in _INVESTMENT_PREDICTION_KEYWORDS
    )


def _contains_legal_signal(text: str) -> bool:
    return any(keyword in text for keyword in _LEGAL_SIGNAL_KEYWORDS)


def _is_legal_domain_question(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized or _is_out_of_scope_request(normalized):
        return False
    return _contains_legal_signal(normalized) or bool(_extract_legal_topic_tags(normalized))


def _effective_citation_strict(req: ChatRequest | None, default: bool) -> bool:
    if req is not None and req.citation_strict is not None:
        return req.citation_strict
    return default


def _effective_temperature(req: ChatRequest | None, default: float) -> float:
    value = req.temperature if req is not None and req.temperature is not None else default
    return min(1.0, max(0.0, float(value)))


def _effective_max_tokens(req: ChatRequest | None, default: int) -> int:
    value = req.max_tokens if req is not None and req.max_tokens is not None else default
    return min(4096, max(128, int(value)))


def _out_of_scope_answer(req: ChatRequest) -> AnswerJson:
    text = (req.text or "").strip().lower()
    if _is_investment_prediction_request(text):
        conclusion = "我只能提供法律普法相关帮助，无法预测股票涨跌或提供投资建议。"
    else:
        conclusion = "我只能提供法律普法相关帮助，无法处理该领域请求。"

    return AnswerJson(
        conclusion=conclusion,
        analysis=[],
        actions=[],
        assumptions=[],
        follow_up_questions=[_OUT_OF_SCOPE_FOLLOW_UP],
        citations=[],
        emotion="calm",
    )


def _legal_domain_no_citation_answer(req: ChatRequest, answer: AnswerJson | None = None) -> AnswerJson:
    tags = _extract_legal_topic_tags(req.text)
    if "rent" in tags:
        conclusion = "该问题属于租赁押金纠纷，但当前本地知识库未检索到足够可核验依据。请补充租赁合同约定、押金金额、房东扣押理由等信息。"
    else:
        conclusion = "该问题属于法律咨询场景，但当前本地知识库未检索到足够可核验依据。请补充关键事实后再继续判断。"

    follow_ups = _build_follow_up_questions(req.text)
    if answer and answer.follow_up_questions:
        follow_ups = list(dict.fromkeys([*answer.follow_up_questions, *follow_ups]))[:4]
    return AnswerJson(
        conclusion=conclusion,
        analysis=[],
        actions=[
            "先整理合同、聊天记录、付款凭证、交接记录等证据。",
            "补充争议金额、对方理由和已经沟通的过程后，再进行更精确判断。",
        ],
        assumptions=[],
        follow_up_questions=follow_ups,
        citations=[],
        emotion="supportive",
    )


def _looks_like_no_evidence_answer(text: str) -> bool:
    normalized = _strip_citation_sentinel(text).strip()
    extra_markers = ("无法提供有效解答", "无法准确回答")
    return any(marker in normalized for marker in (*_NO_BASIS_MARKERS, *extra_markers))


def _answer_disclaims_no_basis(answer: AnswerJson) -> bool:
    answer_text = " ".join([answer.conclusion, *answer.analysis, *answer.actions])
    return any(marker in answer_text for marker in _NO_BASIS_MARKERS)


def _filter_relevant_citations(
    req: ChatRequest | None,
    answer: AnswerJson,
    evidence: list[dict[str, Any]],
    citations: list[Citation],
) -> list[Citation]:
    if not citations:
        return []
    if req is not None and _is_out_of_scope_request(req.text):
        return []
    if _answer_disclaims_no_basis(answer):
        return []

    evidence_map = {str(item.get("chunk_id")): item for item in evidence if item.get("chunk_id")}
    filtered: list[Citation] = []
    seen: set[str] = set()
    for citation in citations:
        chunk_id = str(citation.chunk_id or "")
        if not chunk_id or chunk_id in seen:
            continue
        item = evidence_map.get(chunk_id)
        if item is None:
            continue
        if _is_citation_relevant_to_answer(req.text if req else "", answer, item):
            filtered.append(citation)
            seen.add(chunk_id)
    return filtered


def _is_citation_relevant_to_answer(req_text: str, answer: AnswerJson, evidence_item: dict[str, Any]) -> bool:
    query_tags = _extract_legal_topic_tags(req_text)
    if not query_tags:
        return True

    citation_text = _evidence_topic_text(evidence_item)
    evidence_tags = _extract_legal_topic_tags(citation_text)
    if query_tags & evidence_tags:
        return True

    answer_text = " ".join([answer.conclusion, *answer.analysis, *answer.actions])
    answer_tags = _extract_legal_topic_tags(answer_text)
    return bool(query_tags & answer_tags & evidence_tags)


def _extract_legal_topic_tags(text: str) -> set[str]:
    normalized = _expand_legal_topic_text(text)
    tags: set[str] = set()
    for tag, keywords in _LEGAL_TOPIC_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            tags.add(tag)
    return tags


def _expand_legal_topic_text(text: str) -> str:
    normalized = (text or "").lower()
    additions: list[str] = []
    for triggers, synonyms in _LEGAL_TOPIC_SYNONYMS:
        if any(trigger in normalized for trigger in triggers):
            additions.extend(synonyms)
    if additions:
        return f"{normalized} {' '.join(additions)}"
    return normalized


def _evidence_topic_text(item: dict[str, Any]) -> str:
    parts = [
        item.get("law_name"),
        item.get("article_no"),
        item.get("section"),
        item.get("source"),
        item.get("case_id"),
        item.get("case_name"),
        item.get("text"),
    ]
    return " ".join(str(part) for part in parts if part)


def _fallback_relevant_citations(req: ChatRequest | None, answer: AnswerJson, evidence: list[dict[str, Any]]) -> list[Citation]:
    if req is None or not _is_legal_domain_question(req.text) or _is_out_of_scope_request(req.text):
        return []
    if _answer_disclaims_no_basis(answer):
        return []
    query_tags = _extract_legal_topic_tags(req.text)
    if not query_tags:
        return []
    strong_evidence = [
        item for item in evidence if query_tags & _extract_legal_topic_tags(_evidence_topic_text(item))
    ]
    return _filter_relevant_citations(req, answer, strong_evidence, _to_citations(strong_evidence))[:_ANSWER_EVIDENCE_LIMIT]


def _finalize_answer(
    answer: AnswerJson,
    evidence: list[dict[str, Any]],
    default_emotion: str,
    strict_citation_check: bool,
    req: ChatRequest | None = None,
) -> AnswerJson:
    evidence_chunk_ids = {str(item.get("chunk_id")) for item in evidence if item.get("chunk_id")}
    citations = answer.citations

    if strict_citation_check:
        citations = [citation for citation in answer.citations if citation.chunk_id in evidence_chunk_ids]
        if not citations:
            citations = _fallback_relevant_citations(req, answer, evidence)
    elif not citations:
        citations = _fallback_relevant_citations(req, answer, evidence)

    citations = _filter_relevant_citations(req, answer, evidence, citations)

    emotion = (answer.emotion or default_emotion or "calm").strip().lower()
    if emotion not in {"calm", "serious", "supportive", "warning"}:
        emotion = default_emotion or "calm"

    if strict_citation_check and evidence and not citations:
        if req is not None and _is_legal_domain_question(req.text):
            return _legal_domain_no_citation_answer(req, answer)
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
        conclusion=_strip_citation_sentinel(answer.conclusion).strip() if answer.conclusion else "当前暂无法输出稳定结论，请补充事实后继续。",
        analysis=[item.strip() for item in answer.analysis if item.strip()][:2],
        actions=[item.strip() for item in answer.actions if item.strip()][:2],
        assumptions=[item.strip() for item in answer.assumptions if item.strip()],
        follow_up_questions=[item.strip() for item in answer.follow_up_questions if item.strip()],
        citations=citations,
        emotion=emotion,
    )


def rewrite_query(history: list[dict[str, str]], current_query: str) -> str:
    if not history:
        return current_query
    if not _should_rewrite_query(current_query):
        return current_query

    rule_rewritten = _rewrite_query_by_rules(history, current_query)
    if rule_rewritten is not None:
        return rule_rewritten
    
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


def _should_rewrite_query(current_query: str) -> bool:
    text = (current_query or "").strip()
    if not text:
        return False
    # For complete, standalone questions (even if short), avoid history concatenation.
    if _is_self_contained_query(text):
        return False
    if any(hint in text for hint in _REWRITE_HINTS):
        return True
    return any(pattern in text for pattern in _USER_REFERENTIAL_PATTERNS)


def _rewrite_query_by_rules(history: list[dict[str, str]], current_query: str) -> str | None:
    text = (current_query or "").strip()
    if not text:
        return None

    if _is_self_contained_query(text):
        return None

    last_user = _last_history_message(history, "user")
    if not last_user:
        return None

    # If the current turn already contains enough legal-topic keywords, keep it as-is.
    if len(text) >= 12 and not _contains_reference_hint(text):
        return text

    candidate = text
    if text == last_user:
        return text

    if _contains_reference_hint(text) or len(text) <= 18:
        candidate = f"{last_user}；补充问题：{text}"

    if len(candidate) > 120:
        candidate = candidate[:120].rstrip("；，, ")
    return candidate if candidate != text else None


def _last_history_message(history: list[dict[str, str]], role: str) -> str:
    for message in reversed(history):
        if message.get("role") != role:
            continue
        content = str(message.get("content") or "").strip()
        if content:
            return content
    return ""


def _contains_reference_hint(text: str) -> bool:
    if any(hint in text for hint in _REWRITE_HINTS):
        return True
    return any(pattern in text for pattern in _USER_REFERENTIAL_PATTERNS)


def _is_self_contained_query(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return False
    if _contains_reference_hint(normalized):
        return False
    if any(keyword in normalized for keyword in _QUERY_SELF_CONTAINED_KEYWORDS):
        return True
    # A direct interrogative sentence with explicit legal-topic nouns is typically self-contained.
    if normalized.endswith(("?", "？")) and len(normalized) >= 8:
        return True
    return False


def _trim_evidence_item(item: dict[str, Any]) -> dict[str, Any]:
    trimmed = dict(item)
    text = str(trimmed.get("text") or "").replace("\n", " ").strip()
    trimmed["text"] = text[:120]
    return trimmed


def _build_answer_messages(req: ChatRequest, evidence: list[dict[str, Any]], history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    system_prompt = (
        "你是高校法律普法助手。只能依据给定依据回答，禁止编造法条。"
        "输出严格 JSON，不要 markdown，不要解释。"
        '格式：{"conclusion":"一句结论","analysis":["最多2条分析"],"actions":["最多2条建议"],'
        '"emotion":"calm","citation_chunk_ids":["chunk_id"]}。'
        "citation_chunk_ids 只能填写给定 chunk_id。"
    )
    evidence_text = _render_evidence_text(evidence)
    if evidence_text != "无":
        system_prompt += f"\n依据：\n{evidence_text}"

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_trim_history_messages(history))
    messages.append({"role": "user", "content": req.text.strip()[:240]})
    return messages


def _build_stream_messages(req: ChatRequest, evidence: list[dict[str, Any]], history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    system_prompt = (
        "你是高校法律普法助手。只能依据给定依据回答，禁止编造法条。"
        "先直接输出自然中文答案，不要 markdown。"
        "最后单独一行输出 [[CITATIONS:chunk_id_1,chunk_id_2]]，chunk_id 只能来自给定依据。"
        "正文结构：先给结论，再用“建议：”给出最多2条建议。"
    )
    evidence_text = _render_evidence_text(evidence)
    if evidence_text != "无":
        system_prompt += f"\n依据：\n{evidence_text}"

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_trim_history_messages(history))
    messages.append({"role": "user", "content": req.text.strip()[:240]})
    return messages


def _trim_history_messages(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if not history:
        return []
    trimmed: list[dict[str, str]] = []
    for item in history[-_ANSWER_HISTORY_LIMIT:]:
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        trimmed.append({"role": role, "content": content[:180]})
    return trimmed


def _resolve_llm_model(model_variant: str) -> str:
    if model_variant == "fast":
        return settings.resolved_fast_llm_model() or settings.resolved_llm_model()
    return settings.resolved_llm_model()


def _chat_completion_text(messages: list[dict[str, str]], model: str, max_tokens: int, temperature: float = 0.2) -> str | None:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    body = _chat_completion_request(payload)
    if body is None:
        return None
    try:
        raw = json.loads(body)
        return raw["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        logger.warning("LLM response parse error: %s", e)
        return None


def _chat_completion_stream(messages: list[dict[str, str]], model: str, max_tokens: int, temperature: float = 0.2) -> Iterator[str]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": False},
    }
    req_obj = request.Request(
        url=f"{settings.resolved_llm_base_url()}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.resolved_llm_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req_obj, timeout=get_runtime_config().timeout_sec) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if not line or line == "[DONE]":
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                delta = ((chunk.get("choices") or [{}])[0].get("delta") or {})
                content = delta.get("content")
                if isinstance(content, str) and content:
                    yield content
    except error.HTTPError as e:
        logger.warning("LLM HTTPError: %s", e)
    except error.URLError as e:
        logger.warning("LLM URLError: %s", e)
    except TimeoutError:
        logger.warning("LLM timeout")


def _chat_completion_request(payload: dict[str, Any]) -> str | None:
    req_obj = request.Request(
        url=f"{settings.resolved_llm_base_url()}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.resolved_llm_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req_obj, timeout=get_runtime_config().timeout_sec) as resp:
            return resp.read().decode("utf-8")
    except error.HTTPError as e:
        logger.warning("LLM HTTPError: %s", e)
        return None
    except error.URLError as e:
        logger.warning("LLM URLError: %s", e)
        return None
    except TimeoutError:
        logger.warning("LLM timeout")
        return None


def _extract_stream_citations(content: str) -> tuple[str, list[str]]:
    text = (content or "").strip()
    match = re.search(r"\[\[CITATIONS:([^\]]*)\]\]", text, re.IGNORECASE)
    if not match:
        return _strip_citation_sentinel(text), []
    chunk_ids = [item.strip() for item in match.group(1).split(",") if item.strip()]
    cleaned = (text[: match.start()] + text[match.end() :]).strip()
    return cleaned, chunk_ids[:3]


def _strip_citation_sentinel(text: str) -> str:
    return re.sub(r"\s*\[\[CITATIONS:[^\]]*\]\]\s*", " ", text or "", flags=re.IGNORECASE).strip()
