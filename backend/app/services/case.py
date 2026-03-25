import json
import logging
import uuid
from typing import Any
from urllib import error, request

from app.core.config import settings
from app.schemas.case import CaseResponse, CaseStartRequest, CaseStepRequest
from app.schemas.common import Citation
from app.services import session_store

logger = logging.getLogger(__name__)

# ── 著名案件库 ──────────────────────────────────────────────────────────
CASE_CATALOG: list[dict[str, Any]] = [
    {
        "case_id": "peng_yu_case",
        "title": "彭宇案：扶老人反被讹",
        "category": "民事侵权",
        "difficulty": "⭐⭐",
        "summary": "2006 年南京，青年彭宇扶起一名摔倒老太太并送往医院，后被老太太起诉索赔。法院一审判决彭宇承担部分赔偿，引发社会对「扶不扶」的广泛讨论。",
        "background": (
            "2006年11月20日，南京市民彭宇在公交站台扶起了摔倒的老太太徐某，并送她去医院就诊。"
            "此后，徐某将彭宇告上法庭，声称是彭宇撞倒了她，要求赔偿医疗费等共计13万余元。"
            "彭宇否认撞人，称自己是好心助人。双方各执一词，没有直接的监控视频证据。"
            "案件审理过程中，法官基于'常理推断'作出了争议性判决。"
        ),
        "plaintiff": "徐某（摔倒老太太）",
        "defendant": "彭宇（扶人青年）",
        "key_evidence": ["彭宇承认第一个到达现场并扶起老太太", "无直接监控录像", "医院病历记录", "多名目击证人但证词不一致"],
        "legal_issues": ["侵权责任认定", "举证责任分配", "因果关系推定", "公序良俗与司法导向"],
        "real_verdict": "一审法院判决彭宇承担40%责任，赔偿45876元。后二审期间双方和解。",
    },
    {
        "case_id": "xu_ting_case",
        "title": "许霆案：ATM机多吐钱",
        "category": "刑事犯罪",
        "difficulty": "⭐⭐⭐",
        "summary": "2006 年广州，许霆利用 ATM 机故障多次取款 17.5 万元，一审被判无期徒刑引发社会争议，重审后改判 5 年有期徒刑。",
        "background": (
            "2006年4月21日晚，许霆到广州市某银行ATM机取款100元，发现银行卡只扣了1元，"
            "账户余额为170余元。之后，许霆利用ATM机故障反复取款，先后171次取出17.5万元。"
            "许霆在取到钱后离开广州，直到2007年5月被抓获归案。"
            "银行报案后，公安机关以盗窃罪对许霆立案侦查。"
        ),
        "plaintiff": "广州市人民检察院（公诉方）",
        "defendant": "许霆",
        "key_evidence": ["ATM机取款记录171次", "银行卡交易流水", "ATM机故障日志", "许霆取款后离开广州的行踪记录"],
        "legal_issues": ["盗窃罪的构成要件", "盗窃金融机构vs普通盗窃", "量刑与罪刑相适应原则", "ATM机故障的责任分担"],
        "real_verdict": "一审以盗窃金融机构罪判处无期徒刑。重审改判有期徒刑5年，罚金2万元。",
    },
    {
        "case_id": "yao_jiaxin_case",
        "title": "药家鑫案：交通肇事后杀人",
        "category": "刑事犯罪",
        "difficulty": "⭐⭐⭐⭐",
        "summary": "2010 年西安，大学生药家鑫驾车撞伤行人后，因担心被记下车牌号而持刀将伤者杀害，最终被判处死刑。",
        "background": (
            "2010年10月20日深夜，西安音乐学院大三学生药家鑫驾车将骑电动车的女服务员张妙撞倒。"
            "下车后，药家鑫发现张妙正试图看他的车牌号，于是拿出随身携带的水果刀，"
            "朝张妙身上连捅8刀，导致张妙当场死亡。之后药家鑫驾车逃离现场，途中又撞伤两人。"
            "药家鑫于2010年10月23日向公安机关投案自首。"
        ),
        "plaintiff": "西安市人民检察院（公诉方） / 被害人家属附带民事诉讼",
        "defendant": "药家鑫",
        "key_evidence": ["药家鑫投案自首的供述", "作案凶器（水果刀）", "现场监控和目击证人", "法医鉴定报告：死者身上8处刀伤"],
        "legal_issues": ["故意杀人罪认定", "自首情节的量刑影响", "民意与司法独立", "死刑适用标准"],
        "real_verdict": "一审判处死刑，二审维持原判。2011年6月7日执行死刑。",
    },
    {
        "case_id": "kunshan_defense_case",
        "title": "昆山龙哥案：正当防卫",
        "category": "刑事犯罪",
        "difficulty": "⭐⭐⭐",
        "summary": "2018 年昆山，纹身男刘海龙持刀追砍于海明，刀脱手后于海明拾刀反击，致刘海龙死亡。最终被认定为正当防卫，不负刑事责任。",
        "background": (
            "2018年8月27日晚，江苏昆山市一路口，刘海龙驾驶宝马轿车违章驶入非机动车道，"
            "与正常骑车的于海明发生争执。刘海龙先用拳头击打于海明，随后返回车内取出一把长刀，"
            "对于海明进行砍击。在砍击过程中，刀脱手落地，于海明捡起刀进行反击，"
            "砍中刘海龙数刀。刘海龙受伤后跑向车辆，最终因失血过多死亡。"
        ),
        "plaintiff": "昆山市人民检察院",
        "defendant": "于海明",
        "key_evidence": ["路口监控视频完整记录全过程", "凶器（长刀）", "法医鉴定报告", "刘海龙曾多次受到刑事处罚的前科记录"],
        "legal_issues": ["正当防卫的认定", "防卫过当与正当防卫的界限", "特殊防卫权（无限防卫权）", "持续性不法侵害的判断"],
        "real_verdict": "公安机关认定于海明的行为属于正当防卫，不负刑事责任，撤销案件。检察院表示认同。",
    },
    {
        "case_id": "jiangge_case",
        "title": "江歌案：见义勇为与法律责任",
        "category": "民事+刑事",
        "difficulty": "⭐⭐⭐⭐",
        "summary": "2016 年日本东京，中国留学生江歌为保护室友刘鑫被刘鑫前男友陈世峰杀害。刑事案在日本审理，后民事索赔案在国内审理。",
        "background": (
            "2016年11月3日凌晨，在日本东京，中国留学生江歌在自己公寓门前被室友刘鑫（后改名刘暖曦）的"
            "前男友陈世峰持刀杀害。事发时，刘鑫在公寓内并锁上了门。"
            "陈世峰因纠缠刘鑫不成而行凶。江歌挡在门前试图保护刘鑫，被捅十余刀身亡。"
            "2017年12月，日本法院以故意杀人罪判处陈世峰有期徒刑20年。"
            "2022年1月，江歌母亲在国内起诉刘暖曦（刘鑫），要求其承担民事赔偿责任。"
        ),
        "plaintiff": "江歌母亲江秋莲",
        "defendant": "刘暖曦（刘鑫）",
        "key_evidence": [
            "日本案件审判记录与陈世峰供述",
            "事发前后的微信聊天记录",
            "门锁状态的鉴定与证人证言",
            "江歌与刘鑫的同居关系及帮助行为记录",
        ],
        "legal_issues": ["安全保障义务与注意义务", "受益人的补偿责任", "因果关系与过错认定", "公序良俗原则在侵权中的适用"],
        "real_verdict": "青岛法院一审判决刘暖曦赔偿江秋莲各项损失共计约69.6万元。二审维持原判。",
    },
]


class CaseError(Exception):
    pass


class CaseNotFoundError(CaseError):
    pass


class CaseSessionNotFoundError(CaseError):
    pass


def get_catalog() -> list[dict[str, Any]]:
    """返回可选案件列表（不含详细背景，供前端展示选择卡片）"""
    return [
        {
            "case_id": c["case_id"],
            "title": c["title"],
            "category": c["category"],
            "difficulty": c["difficulty"],
            "summary": c["summary"],
        }
        for c in CASE_CATALOG
    ]


def _find_case(case_id: str) -> dict[str, Any]:
    for c in CASE_CATALOG:
        if c["case_id"] == case_id:
            return c
    raise CaseNotFoundError(f"案件不存在: {case_id}")


def start_case(req: CaseStartRequest) -> CaseResponse:
    case = _find_case(req.case_id)
    session_id = (req.session_id or "").strip() or f"court_{uuid.uuid4().hex[:12]}"

    # 使用 LLM 生成开场白
    opening = _llm_generate_opening(case)

    state = {
        "session_id": session_id,
        "case_id": req.case_id,
        "phase": "opening",          # opening → trial → verdict
        "turn": 0,
        "history": [],               # 对话历史
        "user_choices": [],           # 用户做过的选择
    }

    # 生成第一轮选项
    first_options = _llm_generate_options(case, state, opening)

    session_store.save_session(session_id, req.case_id, state)

    return CaseResponse(
        session_id=session_id,
        case_id=req.case_id,
        text=opening,
        next_question=first_options.get("question", "请选择你的下一步行动："),
        state="opening",
        slots={},
        path=[],
        missing_slots=[],
        next_actions=first_options.get("options", ["查看案件详情", "开始审理"]),
        citations=[],
        emotion="calm",
        audio_url=None,
    )


def step_case(req: CaseStepRequest) -> CaseResponse:
    state = session_store.get_session(req.session_id)
    if not state:
        raise CaseSessionNotFoundError(f"会话不存在: {req.session_id}")

    case = _find_case(state["case_id"])
    user_text = (req.user_input or "").strip()
    user_choice = (req.user_choice or "").strip()
    merged = user_choice or user_text

    state["turn"] = state.get("turn", 0) + 1
    state["user_choices"].append(merged)
    state["history"].append({"role": "user", "content": merged})

    # 判断阶段
    if state["turn"] >= 6:
        state["phase"] = "verdict"

    # 使用 LLM 生成回应
    response_data = _llm_court_step(case, state, merged)

    ai_text = response_data.get("text", "请继续审理案件。")
    state["history"].append({"role": "assistant", "content": ai_text})

    phase = state["phase"]
    options_data = response_data.get("options", {})
    next_question = options_data.get("question", "请选择你的下一步行动：")
    next_actions = options_data.get("options", [])

    # 最终判决阶段
    if phase == "verdict" and not next_actions:
        next_actions = ["无罪 / 不承担责任", "部分责任", "有罪 / 承担全部责任", "查看真实判决结果"]

    session_store.save_session(state["session_id"], state["case_id"], state)

    return CaseResponse(
        session_id=state["session_id"],
        case_id=state["case_id"],
        text=ai_text,
        next_question=next_question,
        state=phase,
        slots={},
        path=[f"第{i+1}轮: {c}" for i, c in enumerate(state["user_choices"])],
        missing_slots=[],
        next_actions=next_actions,
        citations=[],
        emotion=response_data.get("emotion", "calm"),
        audio_url=None,
    )


# ── LLM 调用 ──────────────────────────────────────────────────────────

def _llm_call(system_prompt: str, user_prompt: str) -> str:
    """统一的 LLM 调用"""
    payload = {
        "model": settings.resolved_llm_model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.6,
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
        with request.urlopen(req_obj, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            raw = json.loads(body)
            return raw["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        return ""


def _parse_json_from_text(text: str) -> dict[str, Any]:
    """从 LLM 回复中提取 JSON 对象"""
    import re
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").replace("json", "", 1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _llm_generate_opening(case: dict[str, Any]) -> str:
    system_prompt = (
        "你是一个模拟法庭的AI主持人。用户将扮演法官角色参与案件审理。\n"
        "请用生动、沉浸式的语言介绍案件背景，让用户感到像在真实的法庭中。\n"
        "语气庄重但不失亲和力，类似法律题材影视剧的旁白。\n"
        "不要输出 JSON，直接用自然语言。控制在 200 字以内。"
    )
    user_prompt = (
        f"案件名称：{case['title']}\n"
        f"案件背景：{case['background']}\n"
        f"原告方：{case['plaintiff']}\n"
        f"被告方：{case['defendant']}\n"
        f"关键证据：{', '.join(case['key_evidence'])}\n\n"
        "请生成模拟法庭的开场白，告诉用户他将扮演法官审理此案。"
    )
    result = _llm_call(system_prompt, user_prompt)
    if not result:
        return (
            f"⚖️ 欢迎进入模拟法庭。\n\n"
            f"本案为「{case['title']}」。{case['summary']}\n\n"
            f"原告：{case['plaintiff']}\n"
            f"被告：{case['defendant']}\n\n"
            f"您将以法官身份审理此案，请仔细审查证据，做出公正裁判。"
        )
    return result


def _llm_generate_options(case: dict[str, Any], state: dict[str, Any], context: str) -> dict[str, Any]:
    system_prompt = (
        "你是模拟法庭系统。请根据当前案件状态，为扮演法官的用户生成 2~4 个选项。\n"
        "输出严格 JSON：{\"question\": \"引导问题\", \"options\": [\"选项1\", \"选项2\", ...]}\n"
        "选项要有实质区别，能导向不同的审理方向。不要输出其他内容。"
    )
    user_prompt = (
        f"案件：{case['title']}\n"
        f"当前阶段：{state.get('phase', 'opening')}\n"
        f"当前轮次：第 {state.get('turn', 0)} 轮\n"
        f"上下文：{context[:300]}\n\n"
        "请生成下一步的选项。"
    )
    result = _llm_call(system_prompt, user_prompt)
    parsed = _parse_json_from_text(result)
    if parsed and "options" in parsed:
        return parsed
    return {
        "question": "作为法官，你想如何推进审理？",
        "options": ["传唤证人", "查看关键证据", "听取双方陈述", "直接进入辩论阶段"],
    }


def _llm_court_step(case: dict[str, Any], state: dict[str, Any], user_input: str) -> dict[str, Any]:
    phase = state.get("phase", "trial")
    turn = state.get("turn", 1)
    choices_history = state.get("user_choices", [])
    
    # 检查是否请求查看真实判决
    if "真实判决" in user_input or "real_verdict" in user_input.lower():
        return {
            "text": (
                f"📋 真实判决结果：\n\n{case['real_verdict']}\n\n"
                f"涉及的法律问题：\n" +
                "\n".join(f"• {issue}" for issue in case["legal_issues"]) +
                "\n\n感谢你参与本案的模拟审理！你可以选择其他案件继续体验。"
            ),
            "options": {"question": "你想继续吗？", "options": ["选择其他案件", "再审一次本案"]},
            "emotion": "calm",
        }

    history_text = "\n".join([
        f"{'法官（用户）' if h['role'] == 'user' else '法庭系统'}: {h['content']}" 
        for h in (state.get("history") or [])[-6:]
    ])

    if phase == "verdict":
        system_prompt = (
            "你是模拟法庭的法庭书记官。案件审理已接近尾声，法官（用户）即将做出判决。\n"
            "请用 JSON 回复：\n"
            "{\"text\": \"总结陈词+引导法官宣判\", \"question\": \"判决引导\", "
            "\"options\": [\"判决选项1\", \"判决选项2\", \"判决选项3\", \"查看真实判决结果\"]}\n"
            "总结陈词要回顾审理过程中的关键发现，帮助法官做出最终判断。200字以内。"
        )
    else:
        system_prompt = (
            "你是模拟法庭的AI助手，负责推进庭审进程。用户扮演法官。\n"
            "根据法官的选择/指示，推进法庭审理，呈现证人证词、证据分析、法律辩论等内容。\n"
            "要让审理过程像真实法庭一样生动、有层次感。\n"
            "请用 JSON 回复：\n"
            "{\"text\": \"法庭场景描述（200字以内）\", \"question\": \"下一步引导\", "
            "\"options\": [\"选项1\", \"选项2\", \"选项3\"]}\n"
            "每轮提供 2~4 个有实质区别的选项，引导不同审理方向。"
        )

    user_prompt = (
        f"案件：{case['title']}\n"
        f"背景：{case['background'][:200]}\n"
        f"原告：{case['plaintiff']}，被告：{case['defendant']}\n"
        f"关键证据：{', '.join(case['key_evidence'])}\n"
        f"法律争议点：{', '.join(case['legal_issues'])}\n"
        f"当前轮次：第 {turn} 轮 / 共约 6 轮\n"
        f"审理阶段：{phase}\n"
        f"之前的审理历史：\n{history_text}\n\n"
        f"法官刚刚的选择/指示：{user_input}\n\n"
        "请推进审理并提供下一步选项。"
    )

    result = _llm_call(system_prompt, user_prompt)
    parsed = _parse_json_from_text(result)

    if parsed and "text" in parsed:
        return {
            "text": parsed["text"],
            "options": {
                "question": parsed.get("question", "请选择下一步行动："),
                "options": parsed.get("options", ["继续审理", "查看证据", "进入辩论"]),
            },
            "emotion": parsed.get("emotion", "serious"),
        }
    
    # LLM 返回了纯文本
    if result:
        return {
            "text": result[:500],
            "options": _llm_generate_options(case, state, result[:200]),
            "emotion": "serious",
        }

    # 完全失败的 fallback
    return {
        "text": f"法庭记录：法官选择了「{user_input}」。审理继续进行中...",
        "options": {
            "question": "请选择下一步：",
            "options": ["传唤证人作证", "审查关键证据", "听取律师辩论", "进入最终陈述"],
        },
        "emotion": "serious",
    }
