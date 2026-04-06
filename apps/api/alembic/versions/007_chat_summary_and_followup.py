"""Stage4 structured summary + session follow-up scaffold

Revision ID: 007_summary_fu
Revises: 006_safety
Create Date: 2026-04-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_summary_fu"
down_revision: Union[str, None] = "006_safety"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("chat_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "session_followups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("followup_token", sa.String(length=64), nullable=False),
        sa.Column("contact_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("opt_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_schema_version", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
        sa.UniqueConstraint("followup_token"),
    )


def downgrade() -> None:
    op.drop_table("session_followups")
    op.drop_column("sessions", "chat_summary_json")
