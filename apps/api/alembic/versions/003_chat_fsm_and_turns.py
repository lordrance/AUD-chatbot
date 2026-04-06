"""chat FSM columns and chat_turns

Revision ID: 003_chat_fsm
Revises: 002_survey
Create Date: 2026-04-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_chat_fsm"
down_revision: Union[str, None] = "002_survey"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("chat_user_turns_in_stage", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sessions", sa.Column("chat_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sessions", sa.Column("chat_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sessions", sa.Column("chat_last_turn_index", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sessions", sa.Column("chat_exchange_index", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("sessions", "chat_user_turns_in_stage", server_default=None)
    op.alter_column("sessions", "chat_last_turn_index", server_default=None)
    op.alter_column("sessions", "chat_exchange_index", server_default=None)

    op.create_table(
        "chat_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange_index", sa.Integer(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("arm", sa.String(length=32), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("user_text", sa.Text(), nullable=True),
        sa.Column("assistant_text", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("server_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stub_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_turns_session_id"), "chat_turns", ["session_id"], unique=False)
    op.create_index("ix_chat_turns_session_turn", "chat_turns", ["session_id", "turn_index"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_turns_session_turn", table_name="chat_turns")
    op.drop_index(op.f("ix_chat_turns_session_id"), table_name="chat_turns")
    op.drop_table("chat_turns")
    op.drop_column("sessions", "chat_exchange_index")
    op.drop_column("sessions", "chat_last_turn_index")
    op.drop_column("sessions", "chat_completed_at")
    op.drop_column("sessions", "chat_started_at")
    op.drop_column("sessions", "chat_user_turns_in_stage")
