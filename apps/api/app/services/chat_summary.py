# 模块中文说明：聊天结束时从 slot_json + 基线生成结构化摘要，写入 chat_summary_json。
"""Build structured Stage 4 / chat-end summary from slot_json + baseline (export-friendly)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models.session import SessionRecord
from app.models.survey_response import SurveyResponse
from app.services.chat_fsm import qualified_slot_key

CHAT_SUMMARY_SCHEMA_VERSION = "1"


def _slot(slots: dict[str, Any], stage: int, key: str) -> str | None:
    """从 slot_json 取某阶段某槽位的去空白字符串，空则 None。"""
    v = slots.get(qualified_slot_key(stage, key))
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s or None
    return str(v).strip() or None


def build_chat_summary_dict(row: SessionRecord, db: OrmSession) -> dict[str, Any]:
    """汇总各阶段槽位与基线准备度，生成可写入 chat_summary_json 的 dict。"""
    slots = dict(row.slot_json or {})
    readiness: int | None = None
    q = (
        select(SurveyResponse)
        .where(SurveyResponse.session_id == row.id, SurveyResponse.instrument == "baseline")
        .order_by(SurveyResponse.submitted_at.asc())
        .limit(1)
    )
    bl = db.scalars(q).first()
    if bl and isinstance(bl.answers, dict):
        r = bl.answers.get("readiness_to_change_1_10")
        if isinstance(r, int) and 1 <= r <= 10:
            readiness = r

    top_reason = _slot(slots, 1, "reduce_motivation")
    trigger = _slot(slots, 2, "main_trigger")
    trigger_ctx = _slot(slots, 2, "trigger_context")
    support = _slot(slots, 3, "support_focus")
    micro_plan = _slot(slots, 3, "micro_plan_step")
    takeaway = _slot(slots, 4, "closing_ack")

    conf_parts: list[str] = []
    if readiness is not None:
        conf_parts.append(f"Baseline change readiness {readiness}/10")

    return {
        "schema_version": CHAT_SUMMARY_SCHEMA_VERSION,
        "top_reason_to_cut_down": top_reason,
        "top_trigger_high_risk_situation": trigger,
        "trigger_context": trigger_ctx,
        "support_focus": support,
        "micro_plan_if_then": micro_plan,
        "change_readiness_baseline_1_10": readiness,
        "optional_takeaway": takeaway,
        "confidence_summary": "；".join(conf_parts) if conf_parts else None,
    }


def persist_chat_summary(db: OrmSession, row: SessionRecord) -> None:
    """计算摘要并赋给会话行的 chat_summary_json（调用方负责 commit）。"""
    row.chat_summary_json = build_chat_summary_dict(row, db)
