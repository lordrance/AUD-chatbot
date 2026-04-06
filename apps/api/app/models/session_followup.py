from __future__ import annotations

import uuid
from datetime import datetime

from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionFollowup(Base):
    """7 天随访：每会话一条；含公开 token、联系方式、提交后的问卷 JSON。"""

    __tablename__ = "session_followups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    followup_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    contact_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    opt_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_schema_version: Mapped[str | None] = mapped_column(String(16), nullable=True)

    session: Mapped["SessionRecord"] = relationship("SessionRecord", back_populates="followup")
