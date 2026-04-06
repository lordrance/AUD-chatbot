# 模块中文说明：确定性聊天回复拼装；优先读 YAML 提示词包，缺失时用英文回退文案；不调用 LLM。
"""Deterministic stub: prefer PromptBundle (manifest + YAML) copy; English fallbacks; no LLM calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.chat_fsm import MAX_CHAT_STAGE
from app.services.prompt_registry import PromptBundle, load_bundle


def _warm_neutral(arm: str) -> bool:
    """当前臂是否为共情/温暖条件（empathic）。"""
    return arm == "empathic"


def _arm_style(bundle: PromptBundle, arm: str) -> dict[str, Any]:
    """取 bundle 中对应臂的全局语气块（warm 或 neutral）。"""
    return bundle.warm if arm == "empathic" else bundle.neutral


def _arm_stage_block(bundle: PromptBundle, stage: int, arm: str) -> dict[str, Any]:
    """某阶段 YAML 下 warm 或 neutral 子块（含 transition/slots）。"""
    st = bundle.stages.get(stage) or {}
    ak = "warm" if arm == "empathic" else "neutral"
    block = st.get(ak)
    return block if isinstance(block, dict) else {}


def _style_prefix(bundle: PromptBundle, arm: str, *, transition: bool) -> str:
    """语气前缀：过渡句用 prefix_transition，单槽追问用 prefix_probe。"""
    style = _arm_style(bundle, arm)
    key = "prefix_transition" if transition else "prefix_probe"
    return str(style.get(key) or "")


def _transition_from_bundle(bundle: PromptBundle, arm: str, stage: int) -> str | None:
    """从 YAML 读阶段过渡句；无则返回 None。"""
    block = _arm_stage_block(bundle, stage, arm)
    line = block.get("transition")
    return str(line) if line else None


def _slot_from_bundle(bundle: PromptBundle, arm: str, stage: int, slot: str) -> str | None:
    """从 YAML slots 读某槽位提问句。"""
    block = _arm_stage_block(bundle, stage, arm)
    slots = block.get("slots")
    if not isinstance(slots, dict):
        return None
    v = slots.get(slot)
    return str(v) if v else None


def _transition_line_fallback(arm: str, stage: int) -> str:
    """YAML 缺失时的阶段过渡英文回退文案。"""
    w = _warm_neutral(arm)
    if stage == 0:
        return (
            "Thanks. Next, I'd like to learn about your drinking over the past week."
            if w
            else "Next section: drinking over the past week."
        )
    if stage == 1:
        return (
            "Thanks. Next, let's talk about situations where drinking tends to get heavier."
            if w
            else "Next topic: high-risk drinking situations."
        )
    if stage == 2:
        return (
            "Got it. Let's make a very short coping plan."
            if w
            else "Next section: a brief coping plan."
        )
    if stage == 3:
        return (
            "Great. Let's wrap up and close today's conversation."
            if w
            else "Summary and close."
        )
    return (
        "Thank you for taking part. Please continue with the short post-survey questions. We'll stop here for now."
        if w
        else "Thank you. Please complete the post-survey."
    )


def _slot_question_fallback(arm: str, stage: int, slot: str) -> str:
    """YAML 缺失时按阶段/槽位的英文追问回退。"""
    w = _warm_neutral(arm)
    if stage == 0 and slot == "orientation_ack":
        return (
            "Thanks for your time today. This will take about 20–25 minutes and is text-only. "
            "Please reply briefly to confirm you understand."
            if w
            else "About 20–25 minutes, text-only. Please confirm you understand."
        )
    if stage == 0 and slot == "time_ok":
        return (
            "Is now a good time to continue? (Either way is fine—say what works for you.)"
            if w
            else "Please confirm whether now is a good time to continue."
        )
    if stage == 1 and slot == "recent_drinking":
        return (
            "Roughly how often did you drink in the past week, and about how much each time (standard drinks)?"
            if w
            else "Briefly describe how often you drank in the past week and roughly how much."
        )
    if stage == 1 and slot == "reduce_motivation":
        return (
            "What is the one small thing you most want to change right now?"
            if w
            else "In one sentence, what is your main reason for wanting to drink less?"
        )
    if stage == 2 and slot == "main_trigger":
        return (
            "Which situation most often leads you to drink more than you want?"
            if w
            else "Name the main drinking trigger situation."
        )
    if stage == 2 and slot == "trigger_context":
        return (
            "What usually happens in that situation? (One sentence is enough.)"
            if w
            else "Add a short detail about that situation."
        )
    if stage == 3 and slot == "support_focus":
        return (
            "Today, what single point do you most want support on?"
            if w
            else "Name one concrete point where you need support."
        )
    if stage == 3 and slot == "micro_plan_step":
        return (
            "For that situation, what is one very small step you could try?"
            if w
            else "Give one actionable small step."
        )
    if stage == 4 and slot == "closing_ack":
        return (
            "Anything else to add? If not, reply \"none\"."
            if w
            else "Anything to add? If not, reply \"none\"."
        )
    return "Please keep your reply brief." if w else "Please reply."


def _transition_resolved(bundle: PromptBundle, arm: str, stage: int) -> str:
    """过渡句：优先 bundle，否则回退。"""
    return _transition_from_bundle(bundle, arm, stage) or _transition_line_fallback(arm, stage)


def _slot_resolved(bundle: PromptBundle, arm: str, stage: int, slot: str) -> str:
    """槽位问句：优先 bundle，否则回退。"""
    return _slot_from_bundle(bundle, arm, stage, slot) or _slot_question_fallback(arm, stage, slot)


def _join_probe_and_question(probe: str, question: str) -> str:
    """prefix_probe 与问句之间补空格（中文可无空格，英文需分隔）。"""
    p = (probe or "").strip()
    q = (question or "").strip()
    if not p:
        return q
    if not q:
        return p
    return f"{p} {q}"


def build_assistant_slot_stub(
    arm: str,
    stage_completed: int,
    *,
    completing_chat: bool,
    next_stage: int | None,
    ask_slot: str | None,
    bundle: PromptBundle | None = None,
) -> str:
    """
    拼装本轮助手 stub 文本（过渡句 + 前缀 + 下一槽问句）。
    completing_chat：刚完成第 4 阶段最后一槽；
    next_stage：完成 stage_completed 后进入的阶段，若 completing_chat 且为 None 表示整段聊天结束；
    ask_slot：下一要问的槽位 id。
    """
    if stage_completed < 0 or stage_completed > MAX_CHAT_STAGE:
        raise ValueError("invalid stage")

    b = bundle or load_bundle(None)

    if completing_chat:
        body = _transition_resolved(b, arm, stage_completed)
        return f"{_style_prefix(b, arm, transition=True)}{body}".strip()[:1200]

    if next_stage is not None and ask_slot is not None:
        trans = _transition_resolved(b, arm, stage_completed)
        q = _slot_resolved(b, arm, next_stage, ask_slot)
        head = f"{_style_prefix(b, arm, transition=True)}{trans}".strip()
        tail = _join_probe_and_question(_style_prefix(b, arm, transition=False), q)
        out = f"{head} {tail}".strip() if tail else head
        return out[:1200]

    if ask_slot is not None:
        q = _slot_resolved(b, arm, stage_completed, ask_slot)
        return _join_probe_and_question(_style_prefix(b, arm, transition=False), q)[:1200]

    body = _transition_resolved(b, arm, stage_completed)
    return f"{_style_prefix(b, arm, transition=True)}{body}".strip()[:1200]


def load_strategies_placeholder() -> dict[str, Any]:
    """Load prompts/strategies.json; return placeholder dict if missing."""
    from app.config import settings

    p = Path(settings.prompts_dir) / "strategies.json"
    if not p.is_file():
        return {"version": "0.1", "stub": True, "note": "strategies.json missing"}
    with p.open(encoding="utf-8") as f:
        return json.load(f)
