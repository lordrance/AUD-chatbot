"""Session safety routing v1 fields

Revision ID: 006_safety
Revises: 005_llm
Create Date: 2026-04-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_safety"
down_revision: Union[str, None] = "005_llm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("safety_max_severity", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("sessions", sa.Column("safety_last_routing_action", sa.String(length=64), nullable=True))
    op.add_column(
        "sessions",
        sa.Column("safety_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "safety_policy_chat_ended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("sessions", "safety_max_severity", server_default=None)
    op.alter_column("sessions", "safety_flags", server_default=None)


def downgrade() -> None:
    op.drop_column("sessions", "safety_policy_chat_ended")
    op.drop_column("sessions", "safety_flags")
    op.drop_column("sessions", "safety_last_routing_action")
    op.drop_column("sessions", "safety_max_severity")
