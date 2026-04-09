import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.session import SessionRecord


class ChatTurn(Base):
    """单条聊天轮次（用户/助手），含 exchange 分组、延迟与 stub/LLM 元数据。"""

    __tablename__ = "chat_turns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exchange_index: Mapped[int] = mapped_column(Integer, nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    stage: Mapped[int] = mapped_column(Integer, nullable=False)
    arm: Mapped[str | None] = mapped_column(String(32), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    assistant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp_client_send: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    server_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stub_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["SessionRecord"] = relationship("SessionRecord", back_populates="chat_turns")
