# 模块中文说明：规则型安全扫描（关键词/正则），不涉及 LLM；严重度映射见 severity_to_action。
"""
Deterministic safety routing (v1): keyword/regex only. No LLM involvement.

Severity 0–3 maps to RoutingAction via severity_to_action().
Pre-chat and in-chat share the underlying scan; routing interpretation differs
(see docs/safety-playbook.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from sqlalchemy.orm import Session as OrmSession

from app.models import SurveyResponse


class Severity(IntEnum):
    """规则扫描命中的严重度等级（越高越需干预）。"""

    NONE = 0
    LOW = 1
    MODERATE = 2
    HIGH = 3


class RoutingAction:
    """严重度映射后的路由动作常量（供会话状态与前端提示使用）。"""

    CONTINUE = "CONTINUE"
    SHOW_RESOURCES_AND_CONTINUE = "SHOW_RESOURCES_AND_CONTINUE"
    SHOW_RESOURCES_AND_END_CHAT = "SHOW_RESOURCES_AND_END_CHAT"
    EMERGENCY_STOP = "EMERGENCY_STOP"


def severity_to_action(sev: int) -> str:
    """将 0–3 严重度转为 CONTINUE / 资源提示 / 结束聊天 / 紧急停聊。"""
    if sev <= 0:
        return RoutingAction.CONTINUE
    if sev == 1:
        return RoutingAction.SHOW_RESOURCES_AND_CONTINUE
    if sev == 2:
        return RoutingAction.SHOW_RESOURCES_AND_END_CHAT
    return RoutingAction.EMERGENCY_STOP


# Order matters: first match at highest defined severity wins in scan.
_PATTERN_ROWS: list[tuple[int, str, str]] = [
    (
        Severity.HIGH,
        "si_plan_means",
        r"(自杀|轻生|自尽).{0,20}(跳楼|割腕|服药|上吊|烧炭|方式|怎么死|计划|今晚|马上)",
    ),
    (
        Severity.HIGH,
        "si_immediate_zh",
        r"(不想活|不想活了|去死|死定了|结束了算了|再也撑不下去去死|马上自杀|现在自杀|结束生命)",
    ),
    (
        Severity.HIGH,
        "homicide_zh",
        r"(杀了你|杀了他|杀了她|杀他们|弄死|捅死|投毒害人|报复杀人)",
    ),
    (
        Severity.HIGH,
        "si_immediate_en",
        r"\b(kill\s+myself|end\s+my\s+life|suicide\s+tonight|going\s+to\s+(die|kill))\b",
    ),
    (
        Severity.MODERATE,
        "self_harm_ideation_zh",
        r"(自残|伤害自己|想伤害自己|活不下去|没有意义|撑不下去了|割腕|烧炭)",
    ),
    (
        Severity.MODERATE,
        "substance_crisis_zh",
        r"(过量|中毒了|喝了一箱酒|酒精中毒)",
    ),
    (
        Severity.MODERATE,
        "ideation_vague_en",
        r"\b(self[- ]harm|hurt\s+myself|suicidal\s+thoughts?)\b",
    ),
    (
        Severity.LOW,
        "distress_zh",
        r"(崩溃|绝望|极度痛苦|非常难受|想消失|支撑不住)",
    ),
    (
        Severity.LOW,
        "distress_en",
        r"\b(breaking\s+down|can't\s+cope|cannot\s+cope|overwhelmed|hopeless|falling\s+apart)\b",
    ),
]

_COMPILED: list[tuple[int, str, re.Pattern[str]]] = [
    (sev, code, re.compile(pat, re.IGNORECASE | re.UNICODE)) for sev, code, pat in _PATTERN_ROWS
]


@dataclass(frozen=True)
class SafetyScanResult:
    """单次文本扫描结果：最高严重度与命中的规则码列表。"""

    severity: int
    matched_codes: list[str]


def scan_user_text(text: str) -> SafetyScanResult:
    """对用户文本跑正则规则表，返回最高严重度及所有命中码（去重保序）。"""
    t = (text or "").strip()
    if not t:
        return SafetyScanResult(0, [])
    max_sev = 0
    codes: list[str] = []
    for sev, code, rx in _COMPILED:
        if rx.search(t):
            if sev > max_sev:
                max_sev = int(sev)
            codes.append(code)
    seen: set[str] = set()
    uniq = [c for c in codes if not (c in seen or seen.add(c))]
    return SafetyScanResult(max_sev, uniq)


def merge_session_severity(current_max: int, new_sev: int) -> int:
    """会话级累计最高严重度（取历史与本轮较大值）。"""
    return max(int(current_max or 0), int(new_sev or 0))


def append_safety_flag(row: Any, entry: dict[str, Any]) -> None:
    """向会话行的 safety_flags JSON 数组追加一条扫描/路由记录。"""
    cur = row.safety_flags
    lst: list[Any]
    if isinstance(cur, list):
        lst = list(cur)
    else:
        lst = []
    lst.append(entry)
    row.safety_flags = lst


# Participant-facing policy copy (v1). Replace with IRB-approved wording before production study.
ASSISTANT_EMERGENCY_STOP = (
    "Thank you for your message. The system flagged content that may indicate urgent safety risk. "
    "This research tool does not provide real-time crisis intervention and is not continuously monitored. "
    "If you or someone else is in immediate danger, contact local emergency services (e.g., 911/999/112) "
    "or go to the nearest emergency department. You can also open Help & resources for general support pointers."
)

ASSISTANT_SAFE_END_CHAT = (
    "Under platform safety rules, this research conversation must end here. "
    "This program is not psychotherapy, emergency care, or a substitute for professional treatment. "
    "If you remain distressed or worried about your safety, please reach real-world professional support "
    "and emergency services first; you can open Help & resources anytime. "
    "If the study flow is still available, you may continue to the post-survey (refresh the page or contact the study team if needed)."
)


def _flatten_survey_answers(answers: dict[str, Any] | None) -> str:
    """把问卷 answers 里的字符串与列表项拼成一段纯文本供安全扫描。"""
    if not isinstance(answers, dict):
        return ""
    parts: list[str] = []
    for v in answers.values():
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
        elif isinstance(v, list):
            parts.extend([str(x) for x in v if str(x).strip()])
    return "\n".join(parts)


def pre_chat_text_from_surveys(db: OrmSession, session_id: Any) -> str:
    """聚合资格与基线问卷开放字段文本，用于随机分组前聊前安全闸。"""
    chunks: list[str] = []
    for instrument in ("eligibility", "baseline"):
        row = (
            db.query(SurveyResponse)
            .filter(SurveyResponse.session_id == session_id, SurveyResponse.instrument == instrument)
            .order_by(SurveyResponse.submitted_at.asc())
            .first()
        )
        if row and isinstance(row.answers, dict):
            chunks.append(_flatten_survey_answers(row.answers))
    return "\n\n".join([c for c in chunks if c]).strip()
