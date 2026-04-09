"""Add turn-level metrics fields to chat_turns.

Revision ID: 011_chat_turn_metrics
Revises: 010_observability
Create Date: 2026-04-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_chat_turn_metrics"
down_revision: Union[str, None] = "010_observability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chat_turns", sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("chat_turns", sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("chat_turns", sa.Column("timestamp_client_send", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        UPDATE chat_turns
        SET
          char_count = char_length(COALESCE(text, '')),
          word_count = CASE
            WHEN btrim(COALESCE(text, '')) = '' THEN 0
            ELSE array_length(regexp_split_to_array(btrim(text), E'\\s+'), 1)
          END
        """
    )
    op.alter_column("chat_turns", "char_count", server_default=None)
    op.alter_column("chat_turns", "word_count", server_default=None)


def downgrade() -> None:
    op.drop_column("chat_turns", "timestamp_client_send")
    op.drop_column("chat_turns", "word_count")
    op.drop_column("chat_turns", "char_count")

