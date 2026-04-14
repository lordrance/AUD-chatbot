"""聊天阶段 FSM：按 PDF 扩展槽位；Stage 3 在信心 <7 时强制追加缩小计划槽位。"""

from __future__ import annotations

from typing import Any

# Stage 0–4：每阶段必收槽位（顺序即收集顺序）；Stage0 不收集姓名，仅边界说明 + 就绪（匿名化）。
REQUIRED_SLOTS_BY_STAGE: dict[int, tuple[str, ...]] = {
    0: ("ready_to_start",),
    1: (
        "recent_drinking_pattern",
        "most_concerning_episode",
        "top_reason_to_cut_down",
        "importance_0_10",
        "confidence_0_10",
    ),
    2: (
        "target_situation",
        "where",
        "when",
        "who_with",
        "emotion_or_state",
        "immediate_trigger",
    ),
    3: (
        "selected_strategy",
        "if_then_plan",
        "likely_obstacle",
        "workaround",
        "final_confidence_0_10",
    ),
    4: (
        "summary_reason",
        "summary_trigger",
        "summary_plan",
        "summary_confidence",
        "optional_takeaway",
    ),
}

# Stage 3：首次信心 <7 时必须各填一次（服务器规则，不由模型决定阶段）。
STAGE_3_SHRINK_SLOTS: tuple[str, ...] = ("if_then_plan_revised", "final_confidence_0_10_after_shrink")

MAX_CHAT_STAGE = 4

# 每阶段用户轮次上限（含无效/反复填写同一槽仍计数的轮次）；超出则用占位符填满本阶段并推进。
MAX_USER_TURNS_PER_STAGE: dict[int, int] = {
    0: 8,
    1: 12,
    2: 14,
    3: 16,
    4: 10,
}

# 因达到轮次上限而自动补槽时写入的值（导出可识别）。
CAP_MARKER_MAX_TURNS = "[not_collected:max_turns_per_stage]"


def max_user_turns_for_stage(stage: int) -> int:
    """返回该阶段允许的最大用户发言轮数（达到时尚未收齐则服务器强制补槽）。"""
    return MAX_USER_TURNS_PER_STAGE.get(stage, 20)


# 必须为可解析的 0–10 整数的槽位（键为 (stage, slot_id)）。
NUMERIC_0_10_SLOTS: frozenset[tuple[int, str]] = frozenset(
    {
        (1, "importance_0_10"),
        (1, "confidence_0_10"),
        (3, "final_confidence_0_10"),
        (3, "final_confidence_0_10_after_shrink"),
        (4, "summary_confidence"),
    }
)


def qualified_slot_key(stage: int, slot: str) -> str:
    """生成槽位在 slot_json 中的键，格式为「阶段:槽位名」。"""
    return f"{stage}:{slot}"


def required_slots_for_stage(stage: int) -> tuple[str, ...]:
    """返回某聊天阶段必须收集的槽位 id 元组（不含 Stage 3 条件槽）。"""
    if stage not in REQUIRED_SLOTS_BY_STAGE:
        raise ValueError(f"Invalid chat stage: {stage}")
    return REQUIRED_SLOTS_BY_STAGE[stage]


def parse_rating_0_10(v: Any) -> int | None:
    """解析 0–10 评分；非法则 None。"""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 0 <= v <= 10 else None
    if isinstance(v, float):
        if v.is_integer():
            iv = int(v)
            return iv if 0 <= iv <= 10 else None
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if s.isdigit():
            n = int(s)
            return n if 0 <= n <= 10 else None
    return None


def _is_empty_value(v: Any) -> bool:
    """判断槽位值是否视为未填（None 或空白字符串）。"""
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def slot_value_satisfied(stage: int, slot: str, v: Any) -> bool:
    """槽位是否视为已有效填写（含 0–10 数值槽校验）。"""
    if _is_empty_value(v):
        return False
    if (stage, slot) in NUMERIC_0_10_SLOTS:
        return parse_rating_0_10(v) is not None
    return True


def _stage3_shrink_path_active(slot_json: dict[str, Any]) -> bool:
    """首次 final_confidence_0_10 已为有效整数且 <7 时，必须再填缩小计划与复测信心。"""
    k = qualified_slot_key(3, "final_confidence_0_10")
    conf = parse_rating_0_10(slot_json.get(k))
    return conf is not None and conf < 7


def _first_missing_in_sequence(stage: int, sequence: tuple[str, ...], slot_json: dict[str, Any]) -> str | None:
    for s in sequence:
        k = qualified_slot_key(stage, s)
        if not slot_value_satisfied(stage, s, slot_json.get(k)):
            return s
    return None


def first_missing_slot(stage: int, slot_json: dict[str, Any]) -> str | None:
    """当前阶段第一个尚未有效填写的槽位；已满则返回 None。"""
    base = required_slots_for_stage(stage)
    missing = _first_missing_in_sequence(stage, base, slot_json)
    if missing is not None:
        return missing
    if stage == 3 and _stage3_shrink_path_active(slot_json):
        m = _first_missing_in_sequence(stage, STAGE_3_SHRINK_SLOTS, slot_json)
        if m is not None:
            return m
    return None


def stage_slots_complete(stage: int, slot_json: dict[str, Any]) -> bool:
    """当前阶段全部必填槽是否已有效填写（含 Stage 3 条件缩小槽）。"""
    return first_missing_slot(stage, slot_json) is None


def pad_incomplete_stage_with_cap_marker(stage: int, slot_json: dict[str, Any]) -> bool:
    """将当前阶段未满足槽位填满：文本槽用 CAP_MARKER，0–10 数值槽用 0（可解析且满足校验）。"""
    changed = False
    while not stage_slots_complete(stage, slot_json):
        m = first_missing_slot(stage, slot_json)
        if m is None:
            break
        if (stage, m) in NUMERIC_0_10_SLOTS:
            slot_json[qualified_slot_key(stage, m)] = "0"
        else:
            slot_json[qualified_slot_key(stage, m)] = CAP_MARKER_MAX_TURNS
        changed = True
    return changed


def next_stage_after_completion(current: int) -> int | None:
    """本阶段完成后进入的下一阶段编号；若已是最后一阶段则返回 None。"""
    if current < 0 or current > MAX_CHAT_STAGE:
        raise ValueError(f"Invalid chat stage: {current}")
    if current == MAX_CHAT_STAGE:
        return None
    return current + 1


def initial_current_substate() -> str:
    """随机化后等待填写的第一个槽位（stage:slot）。"""
    first = required_slots_for_stage(0)[0]
    return qualified_slot_key(0, first)


def total_required_slots_count() -> int:
    """全聊天流程「基础」必填槽位数（不含 Stage 3 条件追加的 2 个）。"""
    return sum(len(v) for v in REQUIRED_SLOTS_BY_STAGE.values())
