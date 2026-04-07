"""策略库：answer2.pdf 固定 8 条；Stage3 询问 selected_strategy 时最多向模型暴露 2 条。"""

from __future__ import annotations

import uuid
from typing import Any

# 顺序稳定，便于复现与论文描述
STRATEGY_ORDER: tuple[str, ...] = (
    "delay_first_drink",
    "alternate_with_water",
    "out_of_sight_home",
    "planned_leave_time",
    "text_friend_before",
    "bring_na_beverage",
    "refuse_script",
    "first_urge_substitute",
)

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "delay_first_drink": ("delay", "wait", "minute", "shower", "urge", "first", "home"),
    "alternate_with_water": ("water", "slow", "pace", "party", "dinner", "bar", "social"),
    "out_of_sight_home": ("home", "fridge", "cabinet", "see", "counter", "alone"),
    "planned_leave_time": ("leave", "early", "time", "9", "occasion", "out", "bar"),
    "text_friend_before": ("friend", "text", "message", "alone", "support", "contact"),
    "bring_na_beverage": ("bring", "na", "sparkling", "hand", "party"),
    "refuse_script": ("say no", "refuse", "pressure", "coworker", "round", "script"),
    "first_urge_substitute": ("walk", "snack", "tea", "urge", "substitute", "block"),
}


def pick_offered_strategy_ids(slot_json: dict[str, Any], session_id: uuid.UUID, *, max_offers: int = 2) -> list[str]:
    """据 Stage2 槽位文本粗匹配关键词，不足则按 session_id 哈希补足，始终返回 ≤max_offers 个 id。"""
    blob_parts: list[str] = []
    for k, v in slot_json.items():
        if isinstance(k, str) and k.startswith("2:") and v is not None:
            blob_parts.append(str(v).lower())
    blob = " ".join(blob_parts)

    scored: list[tuple[int, str]] = []
    for sid in STRATEGY_ORDER:
        kws = _KEYWORDS.get(sid, ())
        score = sum(1 for kw in kws if kw in blob)
        scored.append((score, sid))
    scored.sort(key=lambda x: (-x[0], STRATEGY_ORDER.index(x[1])))

    picked: list[str] = []
    for sc, sid in scored:
        if sc > 0 and sid not in picked:
            picked.append(sid)
        if len(picked) >= max_offers:
            return picked[:max_offers]

    h = int(session_id.int % 10_007)
    idx = h % len(STRATEGY_ORDER)
    for i in range(len(STRATEGY_ORDER)):
        sid = STRATEGY_ORDER[(idx + i) % len(STRATEGY_ORDER)]
        if sid not in picked:
            picked.append(sid)
        if len(picked) >= max_offers:
            break
    return picked[:max_offers]


def strategies_payload_for_turn(
    full: dict[str, Any],
    *,
    stage_at_turn: int,
    next_slot_id: str | None,
    slot_json: dict[str, Any],
    session_id: uuid.UUID,
) -> dict[str, Any]:
    """若为 Stage3 且下一槽为 selected_strategy，仅下发两条策略；否则返回完整库。"""
    if stage_at_turn != 3 or next_slot_id != "selected_strategy":
        return full
    ids = pick_offered_strategy_ids(slot_json, session_id)
    all_s = full.get("strategies")
    if not isinstance(all_s, list):
        return {**full, "offered_strategy_ids": ids, "offer_max": 2}
    filt = [x for x in all_s if isinstance(x, dict) and x.get("strategy_id") in ids]
    return {
        **full,
        "strategies": filt,
        "offered_strategy_ids": ids,
        "offer_max": 2,
        "strategy_library_version": full.get("version"),
    }
