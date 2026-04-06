# 模块中文说明：资格未通过等面向参与者的英文展示文案（由 API message 字段返回）。
"""User-facing English copy for ineligibility and similar states."""

INELIGIBLE_MESSAGES: dict[str, str] = {
    "age_below_18": "You must be 18 or older to take part in this study.",
    "audit_c_below_threshold": "Your AUDIT-C total did not meet this study's threshold for hazardous/high-risk drinking.",
    "no_intention_to_reduce": "You indicated you do not currently want to reduce drinking, which does not meet inclusion criteria.",
    "crisis_seeking_emergency_help": "You indicated you need emergency help right now. This study cannot provide that—please use local emergency services or crisis lines (see Help & resources).",
    "crisis_unable_to_complete": "You indicated you are too unwell to complete this session. Please seek appropriate support; you are not eligible to continue the study chat today.",
    "crisis_needs_immediate_clinical": "You indicated you need immediate medical or crisis care. This program is not a substitute—please contact emergency services or a clinician.",
}


def format_ineligible_message(codes: list[str]) -> str:
    """将资格未通过原因码拼成一段参与者可读英文说明。"""
    parts = [INELIGIBLE_MESSAGES[c] for c in codes if c in INELIGIBLE_MESSAGES]
    if not parts:
        return "You are not eligible to continue this study session under the preset rules."
    return " ".join(parts)
