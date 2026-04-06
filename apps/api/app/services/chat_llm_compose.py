# 模块中文说明：拼装单轮聊天 LLM 的 system/user 消息（不发起网络请求）。
"""Build chat-turn LLM messages (no model call)."""

from __future__ import annotations

import json
from typing import Any

from app.services.prompt_registry import PromptBundle


def _json_clip(obj: Any, max_len: int = 6000) -> str:
    """将对象序列化为 JSON 字符串并截断过长内容，用于塞进 prompt。"""
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=2)
    except TypeError:
        s = str(obj)
    if len(s) > max_len:
        return s[:max_len] + "\n…"
    return s


def build_turn_messages(
    *,
    bundle: PromptBundle,
    arm: str,
    stage_at_turn: int,
    current_substate: str | None,
    slot_json: dict[str, Any],
    rolling_summary: str,
    backend_stage_complete: bool,
    mode: str,
    next_slot_id: str | None,
    transition_to_stage: int | None,
    user_just_filled_key: str,
    user_message: str,
    recent_transcript: str,
    strategies: dict[str, Any],
) -> list[dict[str, str]]:
    """根据 bundle、臂、槽位与 transcript 组装单轮 LLM 的 system/user 消息列表。"""
    arm_label = "empathic_warm" if arm == "empathic" else "neutral_professional"
    style_block = _json_clip(bundle.warm if arm == "empathic" else bundle.neutral, 2000)
    global_block = _json_clip(bundle.global_data, 2000)
    stage_block = _json_clip(bundle.stages.get(stage_at_turn, {}), 4000)

    strat = _json_clip(strategies, 2500)

    facts = {
        "stage_at_turn": stage_at_turn,
        "current_substate": current_substate,
        "slot_json": slot_json,
        "rolling_summary": rolling_summary[-4000:],
        "backend_stage_complete": backend_stage_complete,
        "mode": mode,
        "next_slot_id": next_slot_id,
        "transition_to_stage": transition_to_stage,
        "user_just_filled_key": user_just_filled_key,
        "arm": arm,
    }

    system = f"""You are the SafeChat-AUD research text assistant (not treatment). You must:
1) Output only the JSON object required by the API—no Markdown.
2) The server controls stage and randomization; do not suggest changing arm or skipping stages. The JSON field stage_complete is advisory only; the server ignores it for transitions.
3) assistant_text: one or two short sentences in English; tone must match arm={arm_label}.
4) safety_level: integer 0–5; 0 means no risk cues detected; needs_human_review means suggest human review (use true when uncertain).
5) extracted_slot_entries: optional key/value strings extracted from the user's last message; do not invent facts.
6) selected_strategy_ids: strategy ids from the strategy library (empty array if none).

[Global and style]
GLOBAL:
{global_block}

STYLE ({arm_label}):
{style_block}

[Current stage YAML]
{stage_block}

[Strategy library]
{strat}

[Server facts — authoritative]
{json.dumps(facts, ensure_ascii=False, indent=2)}
"""

    user = f"""[This turn user input]
{user_message}

[Recent dialogue, oldest first]
{recent_transcript or "(none)"}
"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
