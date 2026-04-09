import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.session import SessionRecord


class StageStateEvent(Base):
    """阶段状态快照：每次槽位更新/阶段切换追加一行，便于过程分析。"""

    __tablename__ = "stage_state_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    slots_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    stage_complete: Mapped[bool] = mapped_column(nullable=False, default=False)
    reason_for_transition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    importance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_strategy_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    if_then_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    rolling_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["SessionRecord"] = relationship("SessionRecord", back_populates="stage_state_events")
