"""Migrate slot_json/chat_summary_json keys to answer2.pdf names.

Revision ID: 008_pdf_slots
Revises: 007_summary_fu
Create Date: 2026-04-09
"""

from typing import Sequence, Union

from alembic import op

revision: str = "008_pdf_slots"
down_revision: Union[str, None] = "007_summary_fu"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sessions.slot_json key migration (remove stage0 orientation_ack; rename remaining keys)
    op.execute(
        """
        UPDATE sessions
        SET slot_json = (
            SELECT COALESCE(jsonb_object_agg(x.new_key, x.value), '{}'::jsonb)
            FROM (
                SELECT
                    CASE
                        WHEN e.key = '0:orientation_ack' THEN NULL
                        WHEN e.key = '1:recent_pattern' THEN '1:recent_drinking_pattern'
                        WHEN e.key = '1:reason_to_cut_down' THEN '1:top_reason_to_cut_down'
                        WHEN e.key = '1:importance_rating_0_10' THEN '1:importance_0_10'
                        WHEN e.key = '1:confidence_rating_0_10' THEN '1:confidence_0_10'
                        WHEN e.key = '2:target_high_risk_situation' THEN '2:target_situation'
                        WHEN e.key = '2:place' THEN '2:where'
                        WHEN e.key = '2:time' THEN '2:when'
                        WHEN e.key = '2:people' THEN '2:who_with'
                        WHEN e.key = '2:emotion_or_internal_state' THEN '2:emotion_or_state'
                        WHEN e.key = '2:cue_or_trigger' THEN '2:immediate_trigger'
                        WHEN e.key = '3:selected_target_situation' THEN NULL
                        WHEN e.key = '3:obstacle' THEN '3:likely_obstacle'
                        WHEN e.key = '4:top_reason' THEN '4:summary_reason'
                        WHEN e.key = '4:top_trigger' THEN '4:summary_trigger'
                        WHEN e.key = '4:chosen_plan' THEN '4:summary_plan'
                        WHEN e.key = '4:closing_confidence_0_10' THEN '4:summary_confidence'
                        ELSE e.key
                    END AS new_key,
                    e.value
                FROM jsonb_each(COALESCE(sessions.slot_json, '{}'::jsonb)) AS e(key, value)
            ) AS x
            WHERE x.new_key IS NOT NULL
        )
        """
    )

    # sessions.current_substate rename
    op.execute(
        """
        UPDATE sessions
        SET current_substate = CASE current_substate
            WHEN '0:orientation_ack' THEN '0:ready_to_start'
            WHEN '1:recent_pattern' THEN '1:recent_drinking_pattern'
            WHEN '1:reason_to_cut_down' THEN '1:top_reason_to_cut_down'
            WHEN '1:importance_rating_0_10' THEN '1:importance_0_10'
            WHEN '1:confidence_rating_0_10' THEN '1:confidence_0_10'
            WHEN '2:target_high_risk_situation' THEN '2:target_situation'
            WHEN '2:place' THEN '2:where'
            WHEN '2:time' THEN '2:when'
            WHEN '2:people' THEN '2:who_with'
            WHEN '2:emotion_or_internal_state' THEN '2:emotion_or_state'
            WHEN '2:cue_or_trigger' THEN '2:immediate_trigger'
            WHEN '3:selected_target_situation' THEN '3:selected_strategy'
            WHEN '3:obstacle' THEN '3:likely_obstacle'
            WHEN '4:top_reason' THEN '4:summary_reason'
            WHEN '4:top_trigger' THEN '4:summary_trigger'
            WHEN '4:chosen_plan' THEN '4:summary_plan'
            WHEN '4:closing_confidence_0_10' THEN '4:summary_confidence'
            ELSE current_substate
        END
        """
    )

    # existing chat summary keys: keep legacy + add/rename main keys
    op.execute(
        """
        UPDATE sessions
        SET chat_summary_json = (
            COALESCE(chat_summary_json, '{}'::jsonb)
            || jsonb_build_object(
                'schema_version', '4',
                'summary_reason', COALESCE(chat_summary_json->>'summary_reason', chat_summary_json->>'top_reason'),
                'summary_trigger', COALESCE(chat_summary_json->>'summary_trigger', chat_summary_json->>'top_trigger'),
                'summary_plan', COALESCE(chat_summary_json->>'summary_plan', chat_summary_json->>'chosen_plan'),
                'summary_confidence', COALESCE(chat_summary_json->'summary_confidence', chat_summary_json->'closing_confidence_0_10')
            )
        )
        WHERE chat_summary_json IS NOT NULL
        """
    )


def downgrade() -> None:
    # Best-effort reverse mapping for slots/substate.
    op.execute(
        """
        UPDATE sessions
        SET slot_json = (
            SELECT COALESCE(jsonb_object_agg(
                CASE
                    WHEN e.key = '1:recent_drinking_pattern' THEN '1:recent_pattern'
                    WHEN e.key = '1:top_reason_to_cut_down' THEN '1:reason_to_cut_down'
                    WHEN e.key = '1:importance_0_10' THEN '1:importance_rating_0_10'
                    WHEN e.key = '1:confidence_0_10' THEN '1:confidence_rating_0_10'
                    WHEN e.key = '2:target_situation' THEN '2:target_high_risk_situation'
                    WHEN e.key = '2:where' THEN '2:place'
                    WHEN e.key = '2:when' THEN '2:time'
                    WHEN e.key = '2:who_with' THEN '2:people'
                    WHEN e.key = '2:emotion_or_state' THEN '2:emotion_or_internal_state'
                    WHEN e.key = '2:immediate_trigger' THEN '2:cue_or_trigger'
                    WHEN e.key = '3:likely_obstacle' THEN '3:obstacle'
                    WHEN e.key = '4:summary_reason' THEN '4:top_reason'
                    WHEN e.key = '4:summary_trigger' THEN '4:top_trigger'
                    WHEN e.key = '4:summary_plan' THEN '4:chosen_plan'
                    WHEN e.key = '4:summary_confidence' THEN '4:closing_confidence_0_10'
                    ELSE e.key
                END,
                e.value
            ), '{}'::jsonb)
            FROM jsonb_each(COALESCE(sessions.slot_json, '{}'::jsonb)) AS e(key, value)
        )
        """
    )
    op.execute(
        """
        UPDATE sessions
        SET current_substate = CASE current_substate
            WHEN '1:recent_drinking_pattern' THEN '1:recent_pattern'
            WHEN '1:top_reason_to_cut_down' THEN '1:reason_to_cut_down'
            WHEN '1:importance_0_10' THEN '1:importance_rating_0_10'
            WHEN '1:confidence_0_10' THEN '1:confidence_rating_0_10'
            WHEN '2:target_situation' THEN '2:target_high_risk_situation'
            WHEN '2:where' THEN '2:place'
            WHEN '2:when' THEN '2:time'
            WHEN '2:who_with' THEN '2:people'
            WHEN '2:emotion_or_state' THEN '2:emotion_or_internal_state'
            WHEN '2:immediate_trigger' THEN '2:cue_or_trigger'
            WHEN '3:likely_obstacle' THEN '3:obstacle'
            WHEN '4:summary_reason' THEN '4:top_reason'
            WHEN '4:summary_trigger' THEN '4:top_trigger'
            WHEN '4:summary_plan' THEN '4:chosen_plan'
            WHEN '4:summary_confidence' THEN '4:closing_confidence_0_10'
            ELSE current_substate
        END
        """
    )
