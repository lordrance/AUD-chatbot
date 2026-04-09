# 模块中文说明：确定性聊天回复拼装；优先读 YAML 提示词包，缺失时用英文回退文案；不调用 LLM。
"""Deterministic stub: prefer PromptBundle (manifest + YAML) copy; English fallbacks; no LLM calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.arm_styles import style_block_key, style_dict_for_arm
from app.services.chat_fsm import MAX_CHAT_STAGE
from app.services.prompt_registry import PromptBundle, load_bundle


def _arm_style(bundle: PromptBundle, arm: str) -> dict[str, Any]:
    """取 bundle 中对应臂的全局风格块（warm / neutral / supportive_practical）。"""
    return style_dict_for_arm(bundle, arm)


def _arm_stage_block(bundle: PromptBundle, stage: int, arm: str) -> dict[str, Any]:
    """某阶段 YAML 下对应风格子块（含 transition/slots）。"""
    st = bundle.stages.get(stage) or {}
    ak = style_block_key(arm)
    block = st.get(ak)
    if isinstance(block, dict) and block:
        return block
    block_n = st.get("neutral")
    if isinstance(block_n, dict) and block_n:
        return block_n
    block_w = st.get("warm")
    return block_w if isinstance(block_w, dict) else {}


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


# (warm_text, neutral_text) — PDF 对齐槽位英文回退
_SLOT_FALLBACK_PAIR: dict[tuple[int, str], tuple[str, str]] = {
    (0, "preferred_name"): (
        "This is a research chat (not treatment or emergency care), and you can skip questions. "
        "What should we call you? A first name or nickname is fine.",
        "This is a text-only research chat (not treatment or emergency care), and you may skip questions. "
        "Please enter your preferred name or nickname.",
    ),
    (0, "ready_to_start"): (
        "Are you ready to begin now? (If not, a brief note is fine.)",
        "Please confirm you are ready to start now (yes/no or a short note).",
    ),
    (1, "recent_drinking_pattern"): (
        "Over the past week or two, what did your drinking look like overall?",
        "Briefly describe your drinking pattern over the past week or two (frequency and rough amount).",
    ),
    (1, "most_concerning_episode"): (
        "Thinking recently, which time stood out as most concerning for you—and why?",
        "Which recent episode of drinking concerns you most? One sentence is enough.",
    ),
    (1, "top_reason_to_cut_down"): (
        "What matters most to you about drinking less—even one sentence helps.",
        "In one sentence, what is your main reason for wanting to reduce drinking?",
    ),
    (1, "importance_0_10"): (
        "From 0–10, how important is changing your drinking right now? (0 = not important, 10 = extremely.)",
        "Rate from 0 to 10 how important reducing drinking is for you right now.",
    ),
    (1, "confidence_0_10"): (
        "From 0–10, how confident do you feel that you could make a change if you decided to? "
        "(0 = not confident, 10 = very confident.)",
        "Rate from 0 to 10 how confident you are that you could change your drinking if you chose to.",
    ),
    (2, "target_situation"): (
        "Which situation most often pulls you toward drinking more than you want? Pick one priority.",
        "Name the single highest-risk drinking situation you want to focus on.",
    ),
    (2, "where"): (
        "Where does it usually happen?",
        "Where does this situation usually take place?",
    ),
    (2, "when"): (
        "What time of day or week does it tend to happen?",
        "When does this situation tend to occur (time of day, day of week, etc.)?",
    ),
    (2, "who_with"): (
        "Who is usually around in that situation (or who matters there)? Short answer is fine.",
        "Who is typically present or relevant in that situation?",
    ),
    (2, "emotion_or_state"): (
        "What do you tend to feel right before drinking in that moment?",
        "What emotions or internal state show up right before you drink there?",
    ),
    (2, "immediate_trigger"): (
        "What is the clearest cue that makes picking up a drink most likely?",
        "What cue or trigger most strongly leads to drinking in that situation?",
    ),
    (3, "selected_strategy"): (
        "From the strategy ideas we discussed, which one do you want to try first (or your own short label)?",
        "Name one strategy you will try (e.g., delay first drink, alternate with water—your wording).",
    ),
    (3, "if_then_plan"): (
        'Write one if–then plan: "If [trigger], then [small action I will take]."',
        'Give one sentence in "If …, then …" format for your smallest doable step.',
    ),
    (3, "likely_obstacle"): (
        "What is the main obstacle that could get in the way?",
        "What obstacle might make this plan hard?",
    ),
    (3, "workaround"): (
        "What small workaround could help if that obstacle shows up?",
        "What backup tweak could help you stick with the plan?",
    ),
    (3, "final_confidence_0_10"): (
        "From 0–10, how confident are you that you can carry out this plan in the next few days?",
        "Rate 0–10 how confident you are you can follow this plan soon.",
    ),
    (3, "if_then_plan_revised"): (
        "You rated confidence below 7. Please offer a smaller, easier if–then plan—one tiny step only.",
        "Confidence was under 7. Please rewrite a smaller if–then plan that feels more doable.",
    ),
    (3, "final_confidence_0_10_after_shrink"): (
        "After shrinking the plan, what is your confidence now from 0–10?",
        "Rate 0–10 how confident you are in this revised smaller plan.",
    ),
    (4, "summary_reason"): (
        "To close: in one line, what is your top reason for cutting down?",
        "State your main reason to reduce drinking (one line).",
    ),
    (4, "summary_trigger"): (
        "In one line, what is the main trigger situation you focused on?",
        "State the main high-risk situation in one line.",
    ),
    (4, "summary_plan"): (
        "In one line, restate your if–then plan.",
        "Restate your chosen if–then plan in one line.",
    ),
    (4, "summary_confidence"): (
        "From 0–10, how confident are you in this plan as you leave the chat?",
        "Rate 0–10 your confidence in this plan right now.",
    ),
    (4, "optional_takeaway"): (
        "Anything else you want to note? If nothing, reply \"none\".",
        "Optional: anything else to add? If not, reply \"none\".",
    ),
}


def _transition_line_fallback(arm: str, stage: int) -> str:
    """YAML 缺失时的阶段过渡英文回退文案。"""
    k = style_block_key(arm)
    tw = {
        0: {
            "warm": "Thanks. Next we'll look at your recent drinking pattern and what you want to change.",
            "neutral": "Next: recent drinking pattern, a concerning episode, and your reasons to cut down.",
            "supportive_practical": "Good. Next we'll map your recent drinking and your top reason to cut down—small steps.",
        },
        1: {
            "warm": "Thanks. Next we'll narrow in on one high-risk drinking situation and its details.",
            "neutral": "Next topic: one high-risk situation—people, place, time, feelings, and cues.",
            "supportive_practical": "Next we'll zoom in on one risky situation—when, where, who, and triggers.",
        },
        2: {
            "warm": "Got it. Next we'll pick a strategy and shape a very small if–then plan.",
            "neutral": "Next: brief support—choose a strategy and write one if–then micro-plan.",
            "supportive_practical": "Next we'll pick one strategy and a simple if–then you can try.",
        },
        3: {
            "warm": "Great. Let's summarize and close so you can move to the post-survey.",
            "neutral": "Closing: confirm your summary lines, then the post-survey.",
            "supportive_practical": "Next we'll lock your summary lines, then the post-survey.",
        },
    }
    end = {
        "warm": "Thank you for taking part. Please continue with the short post-survey.",
        "neutral": "Thank you. Please complete the post-survey.",
        "supportive_practical": "Thanks—please continue to the short post-survey.",
    }
    if stage in tw:
        return tw[stage][k]
    return end[k]


def _slot_question_fallback(arm: str, stage: int, slot: str) -> str:
    """YAML 缺失时按阶段/槽位的英文追问回退。"""
    k = style_block_key(arm)
    pair = _SLOT_FALLBACK_PAIR.get((stage, slot))
    if pair:
        warm_t, neutral_t = pair
        if k == "warm":
            return warm_t
        if k == "neutral":
            return neutral_t
        return neutral_t
    return "Please keep your reply brief." if k == "warm" else "Please reply."


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
        out = f"{_style_prefix(b, arm, transition=True)}{body}".strip()
        blk = _arm_stage_block(b, stage_completed, arm)
        sign = blk.get("sign_off") or blk.get("closing_sign_off")
        if sign:
            out = f"{out} {str(sign).strip()}".strip()
        return out[:1200]

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
