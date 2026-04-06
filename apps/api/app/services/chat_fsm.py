"""聊天阶段 FSM：以 required_slots / slot_json 为主驱动（无真实槽位抽取）。"""

from __future__ import annotations

from typing import Any

# Stage 0–4：每阶段必须填满的槽位 id（顺序即收集顺序）
REQUIRED_SLOTS_BY_STAGE: dict[int, tuple[str, ...]] = {
    0: ("orientation_ack", "time_ok"),
    1: ("recent_drinking", "reduce_motivation"),
    2: ("main_trigger", "trigger_context"),
    3: ("support_focus", "micro_plan_step"),
    4: ("closing_ack",),
}

MAX_CHAT_STAGE = 4


def qualified_slot_key(stage: int, slot: str) -> str:
    """生成槽位在 slot_json 中的键，格式为「阶段:槽位名」。"""
    return f"{stage}:{slot}"


def required_slots_for_stage(stage: int) -> tuple[str, ...]:
    """返回某聊天阶段必须收集的槽位 id 元组（顺序即提问顺序）。"""
    if stage not in REQUIRED_SLOTS_BY_STAGE:
        raise ValueError(f"Invalid chat stage: {stage}")
    return REQUIRED_SLOTS_BY_STAGE[stage]


def first_missing_slot(stage: int, slot_json: dict[str, Any]) -> str | None:
    """当前阶段第一个尚未填写（或值为空）的槽位 id；若已满则返回 None。"""
    for s in required_slots_for_stage(stage):
        k = qualified_slot_key(stage, s)
        if k not in slot_json or _is_empty_value(slot_json.get(k)):
            return s
    return None


def _is_empty_value(v: Any) -> bool:
    """判断槽位值是否视为未填（None 或空白字符串）。"""
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def stage_slots_complete(stage: int, slot_json: dict[str, Any]) -> bool:
    """当前阶段全部必填槽是否已有非空值。"""
    return first_missing_slot(stage, slot_json) is None


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
    """全聊天流程必填槽位总数（跨阶段累加）。"""
    return sum(len(v) for v in REQUIRED_SLOTS_BY_STAGE.values())


