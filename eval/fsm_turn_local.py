"""
本地（无 DB）复现单轮 chat FSM 与 LLM 组装，与 `post_chat_turn` 槽位/阶段逻辑对齐。
仅用于 eval，不替代生产 controller。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.chat_fsm import (
    first_missing_slot,
    initial_current_substate,
    next_stage_after_completion,
    qualified_slot_key,
    stage_slots_complete,
)
from app.services.chat_llm_compose import build_turn_messages
from app.services.chat_stub_content import build_assistant_slot_stub, load_strategies_placeholder
from app.services.llm_client import call_chat_turn_structured
from app.services.prompt_registry import PromptBundle


@dataclass
class LocalChatState:
    fsm_stage: int = 0
    slot_json: dict[str, Any] = field(default_factory=dict)
    rolling_summary: str = ""
    current_substate: str | None = None

    def __post_init__(self) -> None:
        if self.current_substate is None:
            self.current_substate = initial_current_substate()


def _recent_from_snippets(snippets: list[tuple[str, str]], limit: int = 14) -> str:
    chunk = snippets[-limit:]
    lines = [f"{role}: {text[:800]}" for role, text in chunk]
    return "\n".join(lines)


def apply_user_turn_local(
    *,
    state: LocalChatState,
    arm: str,
    user_message: str,
    bundle: PromptBundle,
    llm_attempted: bool,
    dialogue: list[tuple[str, str]],
) -> tuple[LocalChatState, dict[str, Any]]:
    """
    处理一条用户消息，更新 state，返回 (新 state, 本轮记录 dict)。
    """
    st = state.fsm_stage
    slots: dict[str, Any] = dict(state.slot_json or {})
    target_slot = first_missing_slot(st, slots)
    if target_slot is None:
        raise RuntimeError("No pending slot to fill")

    text_trim = user_message.strip()[:4000]
    fill_key = qualified_slot_key(st, target_slot)
    slots[fill_key] = text_trim

    snippet = text_trim.replace("|", " ")[:160]
    roll = (state.rolling_summary or "") + f"{fill_key}={snippet}|"
    if len(roll) > 12000:
        roll = roll[-12000:]
    state.slot_json = slots
    state.rolling_summary = roll

    stage_complete = stage_slots_complete(st, slots)
    chat_closed = False
    nxt: int | None = None
    if stage_complete:
        nxt = next_stage_after_completion(st)

    next_ask: str | None = None
    first_next: str | None = None
    mode = "next_slot"

    if not stage_complete:
        next_ask = first_missing_slot(st, slots)
        if next_ask is None:
            raise RuntimeError("Slot bookkeeping mismatch")
        mode = "next_slot"
    elif nxt is None:
        mode = "closing"
        chat_closed = True
    else:
        first_next = first_missing_slot(nxt, slots)
        if first_next is None:
            raise RuntimeError("Next stage has no slot definition")
        mode = "transition"

    assistant_stub = build_assistant_slot_stub(
        arm,
        st,
        completing_chat=chat_closed,
        next_stage=nxt if mode == "transition" else None,
        ask_slot=(next_ask if mode == "next_slot" else (first_next if mode == "transition" else None)),
        bundle=bundle,
    )

    assistant_text = assistant_stub
    stub_flag = True
    llm_res = None

    if llm_attempted:
        recent = _recent_from_snippets(dialogue)
        strategies = load_strategies_placeholder()
        next_slot_for_prompt = (
            next_ask if mode == "next_slot" else (first_next if mode == "transition" else None)
        )
        trans_stage = nxt if mode == "transition" else None
        messages = build_turn_messages(
            bundle=bundle,
            arm=arm,
            stage_at_turn=st,
            current_substate=state.current_substate,
            slot_json=slots,
            rolling_summary=state.rolling_summary or "",
            backend_stage_complete=stage_complete,
            mode=mode,
            next_slot_id=next_slot_for_prompt,
            transition_to_stage=trans_stage,
            user_just_filled_key=fill_key,
            user_message=user_message,
            recent_transcript=recent,
            strategies=strategies,
        )
        llm_res = call_chat_turn_structured(messages)
        if llm_res.ok and llm_res.parsed:
            assistant_text = llm_res.parsed.assistant_text[:4000]
            stub_flag = False

    if not stage_complete:
        state.current_substate = qualified_slot_key(st, next_ask)  # type: ignore[arg-type]
    elif chat_closed:
        state.current_substate = None
    else:
        state.fsm_stage = nxt  # type: ignore[assignment]
        state.current_substate = qualified_slot_key(nxt, first_next)  # type: ignore[arg-type]

    dialogue.append(("user", user_message))
    dialogue.append(("assistant", assistant_text))

    stage_after = state.fsm_stage
    record = {
        "user_text": user_message,
        "assistant_text": assistant_text,
        "stub": stub_flag,
        "stage_after": stage_after,
        "chat_closed": chat_closed,
        "prompt_version": bundle.version_ref,
        "llm_error": (llm_res.error if llm_res and not llm_res.ok else None),
        "llm_model": (llm_res.model_version if llm_res else None),
    }
    return state, record
