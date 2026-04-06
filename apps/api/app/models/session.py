from __future__ import annotations

import uuid
from datetime import datetime

from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionRecord(Base):
    """研究会话主表：状态机、随机臂、聊天 FSM 槽位、安全聚合字段与摘要 JSON。"""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="consent_pending")
    arm: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fsm_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dropout_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_bundle_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_document_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ineligible_reasons: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    chat_user_turns_in_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chat_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chat_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chat_last_turn_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chat_exchange_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    current_substate: Mapped[str | None] = mapped_column(String(128), nullable=True)
    slot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rolling_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    safety_max_severity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    safety_last_routing_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safety_flags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    safety_policy_chat_ended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    chat_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    audit_events: Mapped[list["AuditEvent"]] = relationship("AuditEvent", back_populates="session")
    survey_responses: Mapped[list["SurveyResponse"]] = relationship(
        "SurveyResponse", back_populates="session", cascade="all, delete-orphan"
    )
    chat_turns: Mapped[list["ChatTurn"]] = relationship(
        "ChatTurn", back_populates="session", cascade="all, delete-orphan"
    )
    llm_calls: Mapped[list["LlmCall"]] = relationship(
        "LlmCall", back_populates="session", cascade="all, delete-orphan"
    )
    followup: Mapped["SessionFollowup | None"] = relationship(
        "SessionFollowup",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
