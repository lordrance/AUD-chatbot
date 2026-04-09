"""Add API transport/fallback fields to llm_calls.

Revision ID: 009_llm_transport
Revises: 008_pdf_slots
Create Date: 2026-04-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_llm_transport"
down_revision: Union[str, None] = "008_pdf_slots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("llm_calls", sa.Column("api_type", sa.String(length=64), nullable=False, server_default="chat_completions"))
    op.add_column("llm_calls", sa.Column("previous_response_id", sa.String(length=128), nullable=True))
    op.add_column("llm_calls", sa.Column("fallback_reason", sa.Text(), nullable=True))
    op.add_column("llm_calls", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("llm_calls", sa.Column("finish_reason", sa.String(length=64), nullable=True))
    op.add_column("llm_calls", sa.Column("refusal_flag", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.execute(
        "UPDATE llm_calls SET api_type = 'chat_completions' WHERE api_type IS NULL OR api_type = ''"
    )
    op.alter_column("llm_calls", "api_type", server_default=None)
    op.alter_column("llm_calls", "retry_count", server_default=None)
    op.alter_column("llm_calls", "refusal_flag", server_default=None)


def downgrade() -> None:
    op.drop_column("llm_calls", "refusal_flag")
    op.drop_column("llm_calls", "finish_reason")
    op.drop_column("llm_calls", "retry_count")
    op.drop_column("llm_calls", "fallback_reason")
    op.drop_column("llm_calls", "previous_response_id")
    op.drop_column("llm_calls", "api_type")
