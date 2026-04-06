"""
三类轻量自动评分（启发式，供 QA / taxonomy 与人工复核）：
- style_leakage：neutral 臂温情/关系性用语泄漏
- one_question_at_a_time：单轮是否实质只含一个提问焦点
- stage3_micro_plan_specificity：stage_after==3 的助手句是否足够具体（含 if-then 线索等）
"""

from __future__ import annotations

import re
from typing import Any

# neutral 臂下易与 warm 混淆的措辞（可随评审迭代）
_WARM_LEAK_PATTERNS = re.compile(
    r"(抱抱|心疼|特别理解你|懂你|陪你|你不是一个人|我感受到你的|感受到你的|"
    r"真的很不容易|辛苦了|给你一个大大的|温暖的拥抱)",
    re.IGNORECASE,
)

# 明显多任务问法
_MULTI_ASK_PATTERNS = re.compile(
    r"(分别|各自|一是|二是|第一[，,]|第二[，,]|"
    r"既.*又.*\?|既.*又.*？|"
    r"请(同时|一并|分别))",
)

# 具体计划线索
_IF_THEN = re.compile(r"(如果|要是|假如|當|当).{0,40}(就|则|便|先|我会|我就)", re.DOTALL)
_CONCRETE_ACTION = re.compile(
    r"(分钟|点|杯|罐|走|离开|发短信|打电话|喝水|无醇|不买|推迟|先洗澡|深呼吸|拒绝)",
)
_VAGUE_ONLY = re.compile(r"^(注意健康|少喝点|适量|加油|坚持|控制饮酒|不要喝太多)[。!！\s]*$")


def grade_style_leakage(*, arm: str, turns: list[dict[str, Any]]) -> dict[str, Any]:
    if arm != "neutral":
        return {"violation": False, "score": 1.0, "matched_spans": [], "note": "非 neutral 臂，不适用泄漏检测"}
    texts = [(t.get("assistant_text") or "") for t in turns]
    full = "\n".join(texts)
    m = list(_WARM_LEAK_PATTERNS.finditer(full))
    violation = len(m) > 0
    spans = [full[max(0, x.start() - 8) : x.end() + 8] for x in m[:3]]
    score = 0.0 if violation else 1.0
    return {
        "violation": violation,
        "score": score,
        "matched_spans": spans,
        "note": "neutral 下出现温情/关系性模板视为泄漏（需人工确认语境）",
    }


def _question_marks_count(s: str) -> int:
    return s.count("?") + s.count("？")


def _assistant_focus_segment(arm: str, a: str) -> str:
    """去掉常见 probe 前缀后，用后半段统计问句（对齐 stub 里 transition+probe+问句的拼接）。"""
    if arm == "empathic":
        parts = a.split("谢谢你愿意告诉我。")
        return parts[-1].strip() if parts else a
    if arm == "neutral":
        parts = a.split("收到。")
        return parts[-1].strip() if parts else a
    return a


def grade_one_question_at_a_time(*, arm: str, turns: list[dict[str, Any]]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    for i, t in enumerate(turns, start=1):
        a = (t.get("assistant_text") or "").strip()
        if not a:
            continue
        focus = _assistant_focus_segment(arm, a)
        qn = _question_marks_count(focus)
        multi = bool(_MULTI_ASK_PATTERNS.search(focus))
        # 多个问号通常表示多问；中文无问号但「吗…吗」少见，保守用问号计数
        if qn >= 2 or multi:
            violations.append(
                {
                    "turn_index": i,
                    "assistant_preview": a[:200],
                    "focus_preview": focus[:200],
                    "question_marks": qn,
                    "multi_pattern": multi,
                }
            )
    rate = len(violations) / max(1, len(turns))
    return {
        "violation_turns": violations,
        "violation_count": len(violations),
        "score": max(0.0, 1.0 - min(1.0, rate * 2)),
        "note": "双问号或明显并列任务标为可能违规",
    }


def grade_stage3_micro_plan_specificity(*, turns: list[dict[str, Any]]) -> dict[str, Any]:
    stage3_texts = [
        (i, (t.get("assistant_text") or "").strip())
        for i, t in enumerate(turns, start=1)
        if t.get("stage_after") == 3
    ]
    if not stage3_texts:
        return {"violation": True, "score": 0.0, "note": "未找到 stage_after==3 的轮次", "details": []}

    details: list[dict[str, Any]] = []
    vague_hits = 0
    for idx, text in stage3_texts:
        if not text:
            vague_hits += 1
            details.append({"turn_index": idx, "specific": False, "reason": "empty"})
            continue
        has_if_then = bool(_IF_THEN.search(text))
        has_concrete = bool(_CONCRETE_ACTION.search(text))
        vague_short = bool(_VAGUE_ONLY.match(text.strip())) or (len(text) < 40 and not has_concrete)
        specific = (has_if_then or has_concrete) and not vague_short
        if not specific:
            vague_hits += 1
        details.append(
            {
                "turn_index": idx,
                "specific": specific,
                "has_if_then": has_if_then,
                "has_concrete_cue": has_concrete,
                "preview": text[:220],
            }
        )

    score = 1.0 - (vague_hits / max(1, len(stage3_texts)))
    return {
        "violation": vague_hits > 0,
        "vague_count": vague_hits,
        "stage3_turns": len(stage3_texts),
        "score": max(0.0, score),
        "details": details,
        "note": "依赖 if-then/具体行为词；过短且无线索标为不具体",
    }


def grade_session(*, arm: str, turns: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "style_leakage": grade_style_leakage(arm=arm, turns=turns),
        "one_question": grade_one_question_at_a_time(arm=arm, turns=turns),
        "stage3_plan": grade_stage3_micro_plan_specificity(turns=turns),
    }
