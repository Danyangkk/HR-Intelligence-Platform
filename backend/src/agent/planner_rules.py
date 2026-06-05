"""Rule-based intent classification — fallback when LLM planner unavailable."""

from __future__ import annotations

import re
from typing import Any

from src.agent.clarify_helpers import lookup_target_l3s
from src.agent.state import Intent
from src.core.constants import BU_UNITS

_KNOWLEDGE_KEYWORDS = (
    "规定", "制度", "政策", "怎么算", "可以吗", "补偿", "年假", "试用期", "报销",
    "加班费", "哺乳假", "请假流程", "入职流程", "离职流程", "流程是什么", "员工手册",
    "怎么做", "如何做", "如何", "怎么", "需要什么", "哪些动作", "哪些材料", "办理", "手续", "步骤",
)
_LOOKUP_KEYWORDS = (
    "请了", "请假", "几天", "多少天", "合同", "社保", "转正", "绩效", "工资", "花名册",
    "任职", "办了吗", "进度", "状态", "表现", "考核", "评分", "等级", "排名",
)
# 已废弃：旧版关键词主判定列表，被 LLM 语义判定 (PLANNER_SYSTEM §4) 取代。
# 保留仅为兼容旧调用，新代码不应依赖。详见 payroll_safety_net()。
_SALARY_BLOCK = ("薪资明细", "工资明细", "每个人的薪资", "个人薪资", "谁的工资", "工资条", "薪水多少", "工资多少")
_SALARY_ALLOW = ("部门", "事业部", "汇总", "成本", "预算", "平均", "人均")

# 最小薪酬词集合 —— 仅作为"LLM 漏标 payroll_sensitive 时的安全网"。
# 用法：方向只能"更严"——命中 → 当作可能涉密，走二次确认/clarify；绝不能用它放行。
# 不参与"判成什么意图、什么范围"（那是 LLM 的事）。
_PAYROLL_SAFETY_NET_WORDS = (
    "工资", "薪资", "薪酬", "薪水", "奖金", "津贴", "补贴", "提成",
    "年终奖", "工资条", "薪资条", "工资单", "到手", "实发", "应发",
    "工资多少", "挣多少", "收入多少",
)
_NAME_STOP = r"(?=最近|表现|绩效|请假|怎么样|如何|为什么|这|本|个|月|的|在|\d|$|[，,？?])"
_ORG_HEADCOUNT_MARKERS = ("多少人", "多少个人", "几个人", "规模多大", "规模", "人数", "有几个")
NAME_RE = re.compile(rf"[张李王赵周吴郑陈刘韩孙杨][\u4e00-\u9fa5]{{0,1}}{_NAME_STOP}")
_BU_ALIASES = {
    "杭抖": "杭抖部门", "杭综": "杭综部门", "职能": "职能部门",
    "杭抖部门": "杭抖部门", "杭综部门": "杭综部门", "职能部门": "职能部门",
}
_ORG_SCOPE_MARKERS = ("事业部", "部门", "全公司", "公司", "组织", "杭抖", "杭综", "职能")
_ORG_METRIC_MARKERS = (
    "离职率", "入职率", "人均成本", "编制", "编制达成", "出勤率", "离职人数", "在职人数",
)
_FOLLOWUP_MARKERS = ("他", "她", "那", "这", "继续", "还有", "同样", "呢", "也是")
_ALL_INTENT_HINTS = frozenset({"compare", "attribution", "policy", "lookup", "list", "aggregate", "trend", "forecast", "chitchat"})
INTENT_MODE = {
    "chitchat": "闲聊短路",
    "policy": "知识库RAG",
    "lookup": "结构化取数",
    "list": "结构化清单",
    "aggregate": "结构化聚合",
    "trend": "结构化趋势",
    "forecast": "结构化预测",
    "compare": "结构化分析",
    "attribution": "结构化+分析",
}

INTENT_UNMATCHED_MESSAGE = "抱歉哦～ 我没有查到问题的相关答案，可以换个问题试试看呢。"
INTENT_CONFIDENCE_THRESHOLD = 0.45
CHITCHAT_GREETING_REPLY = "你好呀～我是 HR 的超级助手，今天有什么事情可以帮你呢？"
CHITCHAT_FAREWELL_REPLY = "如果之后有任何需要都可以再次询问小助手哦～"
CHITCHAT_INTRO_REPLY = (
    "你好呀～我是 HR 的超级助手，今天有什么事情可以帮你呢？"
    "我可以帮你查数据（考勤/薪酬/编制等）、解读制度政策、做统计对比与趋势分析，也能做离职、绩效等原因诊断。"
)
CHITCHAT_CASUAL_REPLY = (
    "我是专注 HR 领域的小助手～人力数据、制度政策、统计分析我都能帮上忙，有相关问题随时问我哦。"
)
_CHITCHAT_GREET = ("你好", "您好", "hello", "hi", "早上好", "上午好", "下午好", "晚上好", "在吗", "在不在", "嗨", "哈喽")
_CHITCHAT_THANKS = ("谢谢", "感谢", "辛苦了", "多谢", "thanks", "thankyou")
_CHITCHAT_FAREWELL = ("再见", "拜拜", "bye", "回见", "下次见", "再会")
_CHITCHAT_INTRO_MARKERS = (
    "你是谁", "你能干嘛", "你会什么", "你能做什么", "你有什么功能",
    "介绍一下你自己", "介绍你自己", "你能帮什么", "你是做什么的",
)
_CASUAL_CHAT_MARKERS = (
    "天气", "笑话", "故事", "聊聊", "聊天", "无聊", "吃什么", "在干嘛", "干嘛呢",
    "几点了", "心情", "开心", "难过", "随便", "唠嗑",
)
_HR_SUBSTANTIVE_MARKERS = (
    "离职", "绩效", "请假", "编制", "年假", "员工", "事业部", "部门", "考勤",
    "薪资", "工资", "花名册", "入职", "离职率", "对比", "趋势", "多少人", "规定", "制度", "流程",
)


def extract_list_filters(question: str) -> dict[str, Any]:
    """Parse roster list constraints like P5以上."""
    filters: dict[str, Any] = {}
    match = re.search(r"P(\d+)\s*以上", question, re.I)
    if match:
        filters["序列_min"] = f"P{match.group(1)}"
    return filters


def rank_job_level(value: str) -> int:
    match = re.search(r"P(\d+)", str(value or ""), re.I)
    return int(match.group(1)) if match else 0


def filter_roster_rows(rows: list[dict[str, Any]], list_filters: dict[str, Any]) -> list[dict[str, Any]]:
    min_level = list_filters.get("序列_min")
    if not min_level:
        return rows
    threshold = rank_job_level(str(min_level))
    if threshold <= 0:
        return rows
    return [row for row in rows if rank_job_level(str(row.get("序列") or "")) >= threshold]


def is_procedure_question(q: str) -> bool:
    # 「最近表现怎么样」是查人，不是制度流程
    if "怎么样" in q:
        return False
    if any(k in q for k in ("哪些动作", "哪些材料", "怎么做", "如何做", "需要什么", "办理", "手续", "步骤")):
        return True
    if any(k in q for k in ("怎么", "如何")) and not any(k in q for k in ("表现", "绩效", "情况")):
        return True
    if any(topic in q for topic in ("离职", "入职", "辞退")) and any(
        k in q for k in ("动作", "手续", "材料", "流程", "步骤", "怎么", "如何", "需要")
    ):
        return True
    return False


def is_turnover_risk_question(question: str) -> bool:
    q = question.strip()
    return "离职风险" in q or ("风险" in q and "离职" in q and any(k in q for k in ("谁", "哪些", "员工", "名单")))


def is_org_headcount_question(question: str) -> bool:
    """组织/部门人数或规模问法 — 走 aggregate，不是个人 lookup。"""
    q = question.strip()
    if NAME_RE.search(q):
        return False
    has_org = any(m in q for m in _ORG_SCOPE_MARKERS) or any(bu in q for bu in BU_UNITS)
    has_count = any(m in q for m in _ORG_HEADCOUNT_MARKERS)
    return bool(has_org and has_count)


def is_org_structured_question(question: str) -> bool:
    """组织级结构化问法（指标/人数），优先于 LLM 与个人 lookup。"""
    return is_org_metric_question(question) or is_org_headcount_question(question)


def is_org_metric_question(question: str) -> bool:
    """组织/事业部/部门级指标问法 — 不是查某个员工。"""
    q = question.strip()
    if NAME_RE.search(q):
        return False
    if any(k in q for k in ("对比", "相比", "vs", "比较", "谁高", "谁低")):
        return False
    has_org = any(m in q for m in _ORG_SCOPE_MARKERS) or any(bu in q for bu in BU_UNITS)
    has_metric = any(m in q for m in _ORG_METRIC_MARKERS) or ("离职" in q and "率" in q)
    return bool(has_org and has_metric)


def is_followup_with_hint(question: str, intent_hint: str | None) -> bool:
    """多轮追问：短句 + 历史意图，不应走 chitchat 短路。"""
    if not intent_hint or intent_hint in {"chitchat"}:
        return False
    q = question.strip()
    if len(q) > 24:
        return False
    return any(k in q for k in _FOLLOWUP_MARKERS)


def classify_org_metric_intent(question: str) -> Intent | None:
    if not is_org_metric_question(question):
        return None
    q = question.strip()
    if any(k in q for k in ("走势", "趋势", "逐月", "近几个月", "近期变化", "变化情况")):
        return "trend"  # type: ignore[return-value]
    if any(k in q for k in ("为什么", "原因", "偏高", "偏低", "下降", "很差", "较差", "不好")):
        return "attribution"  # type: ignore[return-value]
    return "aggregate"  # type: ignore[return-value]


def is_personal_lookup_question(question: str) -> bool:
    """Only personal data questions should enter lookup + employee resolver."""
    q = question.strip()
    if is_org_metric_question(q):
        return False
    if NAME_RE.search(q):
        return True
    if any(k in q for k in _LOOKUP_KEYWORDS) and not any(m in q for m in _ORG_SCOPE_MARKERS):
        return True
    if any(k in q for k in ("怎么样", "如何")) and any(k in q for k in ("表现", "绩效", "情况", "最近")):
        return True
    return False


def _matches_knowledge_keyword(q: str) -> bool:
    """Match explicit policy/procedure terms; exclude generic 怎么样/闲聊。"""
    if any(k in q for k in ("天气", "新闻", "笑话", "聊天")):
        return False
    for k in _KNOWLEDGE_KEYWORDS:
        if k in ("怎么", "如何"):
            continue
        if k in q:
            return True
    return False


def _is_offtopic_chitchat(q: str, compact: str) -> bool:
    """Other casual chat without HR substance — distinct from greeting/farewell/intro."""
    if any(m in q for m in _CASUAL_CHAT_MARKERS):
        return True
    if len(compact) > 32:
        return False
    if any(q.rstrip().endswith(e) for e in ("吗", "呢", "啊", "呀", "吧")):
        if not any(k in q for k in ("多少", "几个", "谁", "哪些", "怎么算", "规定", "流程", "名单")):
            return True
    return False


def classify_chitchat(question: str) -> dict[str, Any] | None:
    """Return chitchat short-circuit payload, or None when not small talk."""
    q = question.strip()
    if not q:
        return None
    if is_policy_question(q) or is_org_metric_question(q) or NAME_RE.search(q):
        return None
    if any(m in q for m in _HR_SUBSTANTIVE_MARKERS):
        return None

    compact = re.sub(r"[？?！!。，,\s]", "", q)
    lower = compact.lower()

    if any(m in compact for m in _CHITCHAT_INTRO_MARKERS):
        return {"intent": "chitchat", "kind": "intro", "reply": CHITCHAT_INTRO_REPLY}

    if any(f in compact for f in _CHITCHAT_FAREWELL):
        return {"intent": "chitchat", "kind": "farewell", "reply": CHITCHAT_FAREWELL_REPLY}

    if len(compact) <= 12:
        if any(compact == g or compact.startswith(g) or lower == g for g in _CHITCHAT_GREET):
            return {"intent": "chitchat", "kind": "greeting", "reply": CHITCHAT_GREETING_REPLY}
        if any(t in compact for t in _CHITCHAT_THANKS):
            return {"intent": "chitchat", "kind": "greeting", "reply": CHITCHAT_GREETING_REPLY}

    if _is_offtopic_chitchat(q, compact):
        return {"intent": "chitchat", "kind": "casual", "reply": CHITCHAT_CASUAL_REPLY}

    return None


def is_policy_question(question: str) -> bool:
    """True only when the question clearly asks about HR policy/procedure docs."""
    q = question.strip()
    if is_procedure_question(q):
        return True
    if NAME_RE.search(q):
        return False
    if not _matches_knowledge_keyword(q):
        return False
    return not any(k in q for k in _LOOKUP_KEYWORDS)


def classify_intent(question: str, *, hint: str | None = None) -> Intent | None:
    q = question.strip()
    if is_turnover_risk_question(q):
        return "attribution"  # type: ignore[return-value]
    if is_org_headcount_question(q):
        return "aggregate"  # type: ignore[return-value]
    org_metric = classify_org_metric_intent(q)
    if org_metric:
        return org_metric
    if hint in _ALL_INTENT_HINTS and len(q) < 24:
        if any(k in q for k in _FOLLOWUP_MARKERS) and not any(
            k in q for k in (*_KNOWLEDGE_KEYWORDS, "对比", "为什么", "原因", "离职率", "绩效")
        ):
            return hint  # type: ignore[return-value]
    if not is_procedure_question(q):
        if any(k in q for k in ("为什么", "原因")):
            return "attribution"
        if any(k in q for k in ("偏高", "偏低", "下降", "很差", "较差", "不好")):
            return "attribution"
    if any(k in q for k in ("预测", "预计", "下季度", "下月", "缺口")):
        return "forecast"  # type: ignore[return-value]
    if any(k in q for k in ("走势", "趋势", "逐月", "近几个月", "近期变化", "变化情况")):
        return "trend"  # type: ignore[return-value]
    if any(k in q for k in ("名单", "列出", "有哪些人", "人员名单", "员工列表")) or (
        re.search(r"P\d", q, re.I) and any(k in q for k in ("以上", "名单", "员工"))
    ):
        return "list"  # type: ignore[return-value]
    if any(k in q for k in ("汇总", "合计", "总共", "总计", "总天数", "总人数")) and any(
        k in q for k in ("各", "全部", "事业部", "部门", "平均")
    ):
        return "aggregate"  # type: ignore[return-value]
    if any(k in q for k in ("对比", "相比", "vs", "比较", "谁高", "谁低")):
        return "compare"
    has_name = bool(NAME_RE.search(q))
    if has_name and any(k in q for k in _LOOKUP_KEYWORDS):
        return "lookup"
    if has_name and any(k in q for k in ("几天", "多少", "有没有", "是否")):
        return "lookup"
    if has_name and not is_procedure_question(q):
        if "怎么样" in q or ("最近" in q and any(k in q for k in ("表现", "绩效", "假", "考勤", "情况"))):
            return "lookup"
    if is_policy_question(q):
        return "policy"
    if has_name:
        return "lookup"
    return None


def payroll_safety_net(question: str) -> bool:
    """
    薪资关键词安全网（仅在 LLM 漏标 payroll_sensitive 时启用）。

    设计原则（ROUTER §4 出口2 + 用户指示）：
    - LLM 语义判定是唯一分类主路径（判 payroll_sensitive + payroll_scope + intent）；
      关键词不参与判"是什么意图、什么范围"。
    - 关键词仅作"安全网兜底"，方向只能"更严"——
      即"LLM 没标但关键词命中 → 当作可能涉密，走确认/clarify/拦截"，
      绝不能反过来用关键词放行。

    返回 True = LLM 漏标但关键词命中薪酬词 → 应当按可能涉密处理。
    """
    q = question.strip()
    return any(word in q for word in _PAYROLL_SAFETY_NET_WORDS)


def check_salary_rejection(question: str) -> str | None:
    """
    已废弃（DEPRECATED）：旧版基于 _SALARY_BLOCK/_SALARY_ALLOW 关键词的主判定。
    新代码改用 LLM 输出的 `payroll_sensitive` + `payroll_scope` 字段；
    本函数仅为兼容旧测试/旧引用保留，新代码不应再调用。
    """
    q = question.strip()
    if any(k in q for k in _SALARY_BLOCK) and not any(k in q for k in _SALARY_ALLOW):
        return "该问题涉及个人薪资明细，已被拦截，无法回答。"
    return None


def route_payroll_by_scope(question: str) -> dict[str, Any]:
    """
    薪资明细放行后的范围分流（仅在业务超管已确认 TTL 时调用）。
    按 ROUTER §4 出口2 设计 —— 用"主体范围"语义判定，不依赖关键词枚举：
      - 命中人名（NAME_RE）→ individual → 走 lookup
      - 命中事业部三枚举（含别名）→ bu → 走 list
      - 都没命中 → company → 走 clarify（让用户选事业部）

    返回：
      {"kind": "individual", "intent": "lookup"}
      {"kind": "bu", "intent": "list", "事业部": "杭抖部门"}
      {"kind": "company", "intent": "clarify"}
    """
    q = question.strip()

    if NAME_RE.search(q):
        return {"kind": "individual", "intent": "lookup"}

    org = extract_org(q)
    bu = org.get("事业部")
    if bu:
        return {"kind": "bu", "intent": "list", "事业部": bu}

    return {"kind": "company", "intent": "clarify"}


def extract_org(question: str) -> dict[str, Any]:
    org: dict[str, Any] = {}
    for bu in BU_UNITS:
        if bu in question:
            org["事业部"] = bu
            break
    else:
        for key, bu in _BU_ALIASES.items():
            if key in question:
                org["事业部"] = bu
                break
    dept_match = re.search(r"([\u4e00-\u9fa5]{2,6}(?:组|部))", question)
    if dept_match and "事业部" not in dept_match.group(1):
        org["部门"] = dept_match.group(1)
    month_match = re.search(r"(20\d{2}-\d{2})", question)
    if month_match:
        org["统计月份"] = month_match.group(1)
    elif "10月" in question or "十月" in question:
        org["统计月份"] = "2025-10"
    else:
        org["统计月份"] = "2025-10"
    return org


def build_orch_summary(intent: Intent, question: str) -> str:
    labels = {
        "chitchat": "闲聊 · 快捷回复",
        "policy": "制度问答 · 知识库检索",
        "lookup": "个人查询 · 结构化取数",
        "list": "清单查询 · 花名册",
        "aggregate": "聚合统计 · 结构化汇总",
        "trend": "趋势分析 · 时序取数",
        "forecast": "预测分析 · 编制/流动",
        "compare": "对比分析 · 结构化取数",
        "attribution": "归因诊断 · 结构化取数+分析",
    }
    paths = {
        "chitchat": "Planner 短路回复",
        "policy": "Planner → Supervisor → Retriever(RAG) → Composer",
        "lookup": "Planner → Supervisor → Resolver → Retriever(结构化) → Composer",
        "list": "Planner → Supervisor → Resolver → Retriever(结构化) → Composer",
        "aggregate": "Planner → Supervisor → Resolver → Retriever(聚合) → Composer",
        "trend": "Planner → Supervisor → Resolver → Retriever → Analyst → Critic → Composer",
        "forecast": "Planner → Supervisor → Resolver → Retriever → Analyst → Composer",
        "compare": "Planner → Supervisor → Resolver → Retriever → Analyst → Critic → Composer",
        "attribution": "Planner → Supervisor → Resolver → Retriever(并行) → Analyst → Critic → Composer",
    }
    q = question.strip()
    preview = q if len(q) <= 30 else q[:30] + "…"
    return f"{labels.get(intent, intent)} · {preview} · {paths.get(intent, 'Planner → Composer')}"


def build_plan(intent: Intent, question: str, *, entities: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    q = question.strip()
    entities = entities or {}
    if is_turnover_risk_question(q):
        org = extract_org(q)
        scope = org.get("事业部") or org.get("部门") or "目标组织"
        return [
            {"id": "t1", "type": "resolve", "goal": f"解析组织范围：{scope}", "assigned_agent": "Resolver"},
            {
                "id": "t2",
                "type": "retrieve",
                "goal": "取绩效、加班、异动等结构化数据",
                "target_l3": ["l3-5-1-1", "l3-2-2-4", "l3-2-3-1"],
                "assigned_agent": "Retriever",
                "retrieve_mode": "structured",
            },
            {"id": "t3", "type": "analyze", "goal": "离职风险加权识别", "assigned_agent": "Analyst"},
            {"id": "t4", "type": "critique", "goal": "校验证据", "assigned_agent": "Critic"},
            {"id": "t5", "type": "compose", "goal": "输出风险名单与建议（标注非确定）", "assigned_agent": "Composer"},
        ]
    if intent == "policy":
        topic = "离职" if "离职" in q else "入职" if "入职" in q else "年假" if "年假" in q else "制度"
        return [
            {
                "id": "t1", "type": "retrieve",
                "goal": f"RAG 检索员工手册中与「{topic}」相关的现行制度条款",
                "target_l3": ["l3-1-1-1"], "assigned_agent": "Retriever", "retrieve_mode": "rag",
            },
            {"id": "t2", "type": "compose", "goal": "组织制度答案并标注条文出处", "assigned_agent": "Composer"},
        ]
    if intent == "lookup":
        name_match = NAME_RE.search(q)
        who = name_match.group(0) if name_match else "员工"
        target_l3 = entities.get("target_l3") or lookup_target_l3s(entities.get("lookup_scope"))
        if any(k in q for k in ("表现", "绩效", "考核", "评分", "等级", "排名")):
            table = "绩效记录"
            if not entities.get("target_l3") and not entities.get("lookup_scope"):
                target_l3 = lookup_target_l3s("performance")
        elif "假" in q:
            table = "请假记录"
        elif entities.get("lookup_scope") == "attendance":
            table = "加班记录"
        elif entities.get("lookup_scope") == "overview":
            table = "综合近况"
        elif "花名册" in q:
            table = "花名册"
            target_l3 = ["l3-2-1-4"]
        else:
            table = "业务数据"
        return [
            {"id": "t1", "type": "resolve", "goal": f"解析员工实体：{who}", "assigned_agent": "Resolver"},
            {
                "id": "t2", "type": "retrieve", "goal": f"结构化查询 {who} 的{table}",
                "target_l3": list(target_l3), "assigned_agent": "Retriever", "retrieve_mode": "structured",
            },
            {"id": "t3", "type": "compose", "goal": "组织答案并标注数据出处", "assigned_agent": "Composer"},
        ]
    if intent == "compare":
        org = extract_org(q)
        scope = org.get("事业部") or "全部事业部"
        month = org.get("统计月份") or "2025-10"
        return [
            {"id": "t1", "type": "resolve", "goal": f"解析范围：{scope} / {month}", "assigned_agent": "Resolver"},
            {
                "id": "t2", "type": "retrieve", "goal": f"结构化拉取 {month} 成本与编制数据",
                "target_l3": ["l3-4-6-3", "l3-6-1-1"], "assigned_agent": "Retriever", "retrieve_mode": "structured",
            },
            {"id": "t3", "type": "analyze", "goal": "对比人均成本并引用指标口径", "assigned_agent": "Analyst"},
            {"id": "t4", "type": "critique", "goal": "校验证据充分性", "assigned_agent": "Critic"},
            {"id": "t5", "type": "compose", "goal": "组织结论与图表", "assigned_agent": "Composer"},
        ]
    if intent == "attribution":
        org = extract_org(q)
        topic = "离职" if "离职" in q else "绩效" if "绩效" in q else "综合"
        scope = org.get("部门") or org.get("事业部") or "目标组织"
        return [
            {"id": "t1", "type": "resolve", "goal": f"解析归因主题：{topic} · {scope}", "assigned_agent": "Resolver"},
            {
                "id": "t2", "type": "retrieve", "goal": f"结构化多表取数支撑「{topic}」归因",
                "target_l3": ["l3-2-5-1", "l3-2-3-1", "l3-5-1-1"],
                "assigned_agent": "Retriever", "retrieve_mode": "structured",
            },
            {"id": "t3", "type": "analyze", "goal": f"归纳「{topic}」影响因素", "assigned_agent": "Analyst"},
            {"id": "t4", "type": "critique", "goal": "校验证据充分性", "assigned_agent": "Critic"},
            {"id": "t5", "type": "compose", "goal": "组织结论", "assigned_agent": "Composer"},
        ]
    if intent == "list":
        org = extract_org(q)
        scope = org.get("部门") or org.get("事业部") or "全公司"
        return [
            {"id": "t1", "type": "resolve", "goal": f"解析清单范围：{scope}", "assigned_agent": "Resolver"},
            {
                "id": "t2", "type": "retrieve", "goal": f"拉取 {scope} 花名册清单",
                "target_l3": ["l3-2-1-4"], "assigned_agent": "Retriever", "retrieve_mode": "structured",
            },
            {"id": "t3", "type": "compose", "goal": "输出员工名单", "assigned_agent": "Composer"},
        ]
    if intent == "aggregate":
        org = extract_org(q)
        scope = org.get("事业部") or org.get("部门") or "全部事业部"
        month = org.get("统计月份") or "2025-10"
        if is_org_headcount_question(q):
            return [
                {"id": "t1", "type": "resolve", "goal": f"解析组织范围：{scope}", "assigned_agent": "Resolver"},
                {
                    "id": "t2",
                    "type": "retrieve",
                    "goal": f"查询 {scope} 在岗人数",
                    "target_l3": ["l3-2-1-4"],
                    "assigned_agent": "Retriever",
                    "retrieve_mode": "structured",
                },
                {"id": "t3", "type": "compose", "goal": "输出人数并标注口径", "assigned_agent": "Composer"},
            ]
        if "离职率" in q or ("离职" in q and "率" in q):
            return [
                {"id": "t1", "type": "resolve", "goal": f"解析组织范围：{scope} / {month}", "assigned_agent": "Resolver"},
                {
                    "id": "t2", "type": "retrieve", "goal": f"查询 {scope} {month} 离职率数据",
                    "target_l3": ["l3-2-5-1"], "assigned_agent": "Retriever", "retrieve_mode": "structured",
                },
                {"id": "t3", "type": "compose", "goal": "输出组织离职率并标注口径", "assigned_agent": "Composer"},
            ]
        group_by = ["事业部"] if "事业部" in q or not org.get("部门") else ["部门"]
        metric_field = "请假天数" if "假" in q else "加班时长" if "加班" in q else "请假天数"
        target_l3 = "l3-2-2-1" if metric_field == "请假天数" else "l3-2-2-4"
        return [
            {"id": "t1", "type": "resolve", "goal": f"解析聚合范围：{scope} / {month}", "assigned_agent": "Resolver"},
            {
                "id": "t2", "type": "retrieve",
                "goal": f"按 {group_by[0]} 汇总 {metric_field}",
                "target_l3": [target_l3],
                "assigned_agent": "Retriever",
                "retrieve_mode": "structured",
                "group_by": group_by,
                "aggregations": [{"field": metric_field, "op": "sum"}],
            },
            {"id": "t3", "type": "compose", "goal": "输出聚合结果并标注口径", "assigned_agent": "Composer"},
        ]
    if intent == "trend":
        org = extract_org(q)
        scope = org.get("事业部") or org.get("部门") or "目标组织"
        metric = "离职率" if "离职" in q else "指标"
        return [
            {"id": "t1", "type": "resolve", "goal": f"解析趋势范围：{scope} · {metric}", "assigned_agent": "Resolver"},
            {
                "id": "t2", "type": "retrieve", "goal": f"拉取 {scope} 多期 {metric} 数据",
                "target_l3": ["l3-2-5-1"], "assigned_agent": "Retriever", "retrieve_mode": "structured",
            },
            {"id": "t3", "type": "analyze", "goal": f"分析 {metric} 走势", "assigned_agent": "Analyst"},
            {"id": "t4", "type": "critique", "goal": "校验趋势证据", "assigned_agent": "Critic"},
            {"id": "t5", "type": "compose", "goal": "输出趋势结论与图表", "assigned_agent": "Composer"},
        ]
    if intent == "forecast":
        org = extract_org(q)
        scope = org.get("事业部") or org.get("部门") or "目标组织"
        return [
            {"id": "t1", "type": "resolve", "goal": f"解析预测范围：{scope}", "assigned_agent": "Resolver"},
            {
                "id": "t2", "type": "retrieve", "goal": "拉取编制与在岗数据",
                "target_l3": ["l3-6-1-1"], "assigned_agent": "Retriever", "retrieve_mode": "structured",
            },
            {"id": "t3", "type": "analyze", "goal": "估算编制缺口（风险提示非确定）", "assigned_agent": "Analyst"},
            {"id": "t4", "type": "critique", "goal": "校验预测证据", "assigned_agent": "Critic"},
            {"id": "t5", "type": "compose", "goal": "输出预测结论与说明", "assigned_agent": "Composer"},
        ]
    return [{"id": "t1", "type": "compose", "goal": f"暂未实现 {intent}", "assigned_agent": "Composer"}]
