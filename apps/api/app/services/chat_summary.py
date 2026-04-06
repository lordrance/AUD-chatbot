# 模块中文说明：聊天结束时从 slot_json + 基线生成结构化摘要，写入 chat_summary_json。
"""Build structured Stage 4 / chat-end summary from slot_json + baseline (export-friendly)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models.session import SessionRecord
from app.models.survey_response import SurveyResponse
from app.services.chat_fsm import parse_rating_0_10, qualified_slot_key

CHAT_SUMMARY_SCHEMA_VERSION = "2"


def _slot(slots: dict[str, Any], stage: int, key: str) -> str | None:
    """从 slot_json 取某阶段某槽位的去空白字符串，空则 None。"""
    v = slots.get(qualified_slot_key(stage, key))
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s or None
    return str(v).strip() or None


def _stage2_context_blob(slots: dict[str, Any]) -> str | None:
    """将 Stage 2 子槽拼成一段情境摘要。"""
    parts: list[str] = []
    for k in ("people", "place", "time", "emotion_or_internal_state", "cue_or_trigger"):
        t = _slot(slots, 2, k)
        if t:
            parts.append(f"{k}: {t}")
    if not parts:
        return None
    return "; ".join(parts)


def build_chat_summary_dict(row: SessionRecord, db: OrmSession) -> dict[str, Any]:
    """汇总各阶段槽位与基线准备度，生成可写入 chat_summary_json 的 dict。"""
    slots = dict(row.slot_json or {})
    readiness: int | None = None
    importance_baseline: int | None = None
    q = (
        select(SurveyResponse)
        .where(SurveyResponse.session_id == row.id, SurveyResponse.instrument == "baseline")
        .order_by(SurveyResponse.submitted_at.asc())
        .limit(1)
    )
    bl = db.scalars(q).first()
    if bl and isinstance(bl.answers, dict):
        a = bl.answers
        r = a.get("readiness_to_change_1_10")
        if isinstance(r, int) and 1 <= r <= 10:
            readiness = r
        imp = a.get("importance_to_reduce_0_10")
        if isinstance(imp, int) and 0 <= imp <= 10:
            importance_baseline = imp

    preferred_name = _slot(slots, 0, "preferred_name")
    reason_s1 = _slot(slots, 1, "reason_to_cut_down")
    top_reason = _slot(slots, 4, "top_reason") or reason_s1
    top_trigger = _slot(slots, 4, "top_trigger") or _slot(slots, 2, "target_high_risk_situation")
    trigger_ctx = _stage2_context_blob(slots)
    strategy = _slot(slots, 3, "selected_strategy")
    plan_primary = _slot(slots, 3, "if_then_plan")
    plan_rev = _slot(slots, 3, "if_then_plan_revised")
    chosen_plan = _slot(slots, 4, "chosen_plan") or plan_rev or plan_primary
    micro_plan = plan_rev or plan_primary

    conf_close = parse_rating_0_10(slots.get(qualified_slot_key(4, "closing_confidence_0_10")))
    conf_final = parse_rating_0_10(slots.get(qualified_slot_key(3, "final_confidence_0_10")))
    conf_after = parse_rating_0_10(slots.get(qualified_slot_key(3, "final_confidence_0_10_after_shrink")))
    takeaway = _slot(slots, 4, "optional_takeaway")

    conf_parts: list[str] = []
    if readiness is not None:
        conf_parts.append(f"Baseline change readiness {readiness}/10")
    if importance_baseline is not None:
        conf_parts.append(f"Baseline importance to reduce {importance_baseline}/10")
    if conf_final is not None:
        conf_parts.append(f"Plan confidence (first) {conf_final}/10")
    if conf_after is not None:
        conf_parts.append(f"Plan confidence (after shrink) {conf_after}/10")
    if conf_close is not None:
        conf_parts.append(f"Closing confidence {conf_close}/10")

    return {
        "schema_version": CHAT_SUMMARY_SCHEMA_VERSION,
        "preferred_name": preferred_name,
        "top_reason": top_reason,
        "top_trigger": top_trigger,
        "chosen_plan": chosen_plan,
        "closing_confidence_0_10": conf_close,
        "optional_takeaway": takeaway,
        "selected_strategy": strategy,
        "trigger_context": trigger_ctx,
        "micro_plan_if_then": micro_plan,
        "change_readiness_baseline_1_10": readiness,
        "importance_to_reduce_baseline_0_10": importance_baseline,
        "confidence_summary": "；".join(conf_parts) if conf_parts else None,
        # Legacy keys (v1 export) for existing notebooks / specs
        "top_reason_to_cut_down": top_reason,
        "top_trigger_high_risk_situation": top_trigger,
        "support_focus": strategy,
    }


def persist_chat_summary(db: OrmSession, row: SessionRecord) -> None:
    """计算摘要并赋给会话行的 chat_summary_json（调用方负责 commit）。"""
    row.chat_summary_json = build_chat_summary_dict(row, db)
