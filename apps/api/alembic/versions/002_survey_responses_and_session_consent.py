"""survey_responses and session consent fields

Revision ID: 002_survey
Revises: 001_initial
Create Date: 2026-04-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_survey"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sessions", sa.Column("consent_document_version", sa.String(length=64), nullable=True))
    op.add_column("sessions", sa.Column("ineligible_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        "survey_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "instrument", name="uq_survey_session_instrument"),
    )
    op.create_index(op.f("ix_survey_responses_session_id"), "survey_responses", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_survey_responses_session_id"), table_name="survey_responses")
    op.drop_table("survey_responses")
    op.drop_column("sessions", "ineligible_reasons")
    op.drop_column("sessions", "consent_document_version")
    op.drop_column("sessions", "consent_at")
