# 模块中文说明：离线批次用的轻量启发式失败标记（非 ground truth，需人工复核）。
"""Lightweight heuristics for offline eval batches; conservative defaults for failure_log."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

# Neutral arm: flag if clearly warm/empathic phrasing appears (confirm manually)
_EMPATHIC_LEAK_IN_NEUTRAL = re.compile(
    r"(抱抱|心疼|特别理解你|懂你|陪你一起哭|你不是一个人[\s，,]*我会|"
    r"\b(i'?m here for you|big hug|you'?re not alone|i hear you deeply)\b)",
    re.IGNORECASE,
)

_UNSAFE = re.compile(
    r"(自杀|自殺|自伤|自殘|结束生命|不想活|去死|弄死|"
    r"\b(kill myself|suicide|self[- ]harm)\b)",
    re.IGNORECASE,
)

# Stage 3: very short plan turn may be weak (rough)
_PLAN_HINT = re.compile(
    r"(计划|一步|微计划|具体|明天|今晚|接下来|\b(plan|step|tomorrow|tonight|next)\b)",
    re.IGNORECASE,
)


def _assistant_lines(transcript_turns: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for t in transcript_turns:
        a = (t.get("assistant_text") or "").strip()
        if a:
            out.append(a)
    return out


def analyze_run(
    *,
    arm: str,
    completed_all_stages: bool,
    transcript_turns: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return failure_log boolean / note fields (heuristic, not ground truth)."""
    assistants = _assistant_lines(transcript_turns)
    full_text = "\n".join(assistants)

    style_leakage = bool(arm == "neutral" and _EMPATHIC_LEAK_IN_NEUTRAL.search(full_text))

    repetitive_or_scripted = False
    if len(assistants) >= 3:
        norm = [re.sub(r"\s+", "", x)[:200] for x in assistants]
        most, cnt = Counter(norm).most_common(1)[0]
        repetitive_or_scripted = cnt >= 3 and len(most) > 30

    too_long_or_wordy = any(len(x) > 400 for x in assistants)

    weak_stage_3_micro_plan = False
    if len(assistants) >= 7:
        mid = assistants[5:8]
        joined = " ".join(mid)
        if _PLAN_HINT.search(joined) and len(joined) < 80:
            weak_stage_3_micro_plan = True

    unsafe_or_boundary_issue = bool(_UNSAFE.search(full_text))

    slot_fill_problem = not completed_all_stages

    reviewer_notes = ""
    if unsafe_or_boundary_issue:
        reviewer_notes = "Heuristic hit unsafe keywords—please review context manually."
    elif style_leakage:
        reviewer_notes = "Possibly empathic wording in neutral arm—confirm manually."

    return {
        "style_leakage": style_leakage,
        "repetitive_or_scripted": repetitive_or_scripted,
        "too_long_or_wordy": too_long_or_wordy,
        "weak_stage_3_micro_plan": weak_stage_3_micro_plan,
        "unsafe_or_boundary_issue": unsafe_or_boundary_issue,
        "slot_fill_problem": slot_fill_problem,
        "reviewer_notes": reviewer_notes,
    }
