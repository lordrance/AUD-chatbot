import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.session import SessionRecord


class LlmCall(Base):
    """单次 LLM 调用记录：用量、延迟、是否回退、归一化输出与原始内容片段。"""

    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exchange_index: Mapped[int] = mapped_column(Integer, nullable=False)

    prompt_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    api_type: Mapped[str] = mapped_column(String(64), nullable=False, default="chat_completions")
    response_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    previous_response_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finish_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refusal_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    normalized_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["SessionRecord"] = relationship("SessionRecord", back_populates="llm_calls")
