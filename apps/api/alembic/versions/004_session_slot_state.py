"""session slot-driven chat state

Revision ID: 004_slots
Revises: 003_chat_fsm
Create Date: 2026-04-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_slots"
down_revision: Union[str, None] = "003_chat_fsm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("current_substate", sa.String(length=128), nullable=True))
    op.add_column(
        "sessions",
        sa.Column(
            "slot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "sessions",
        sa.Column("rolling_summary", sa.Text(), server_default="", nullable=False),
    )
    op.alter_column("sessions", "slot_json", server_default=None)
    op.alter_column("sessions", "rolling_summary", server_default=None)


def downgrade() -> None:
    op.drop_column("sessions", "rolling_summary")
    op.drop_column("sessions", "slot_json")
    op.drop_column("sessions", "current_substate")
