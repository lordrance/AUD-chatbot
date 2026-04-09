"""Add session meta json and stage_state_events table.

Revision ID: 010_observability
Revises: 009_llm_transport
Create Date: 2026-04-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_observability"
down_revision: Union[str, None] = "009_llm_transport"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "session_meta_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("sessions", "session_meta_json", server_default=None)

    op.create_table(
        "stage_state_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_stage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("slots_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("stage_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reason_for_transition", sa.String(length=64), nullable=True),
        sa.Column("importance_score", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("selected_strategy_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("if_then_plan", sa.Text(), nullable=True),
        sa.Column("rolling_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stage_state_events_session_id", "stage_state_events", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stage_state_events_session_id", table_name="stage_state_events")
    op.drop_table("stage_state_events")
    op.drop_column("sessions", "session_meta_json")
