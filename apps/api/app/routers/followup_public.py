# 模块中文说明：公开随访路由（仅凭 token，无需会话 Bearer）。
"""Tokenized 7-day follow-up submit (no session Bearer)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.constants import SURVEY_SCHEMA_FOLLOWUP_7D
from app.database import get_db
from app.models.audit_event import AuditEvent
from app.models.session import SessionRecord
from app.models.session_followup import SessionFollowup
from app.schemas.followup import FollowUpSubmitOkResponse, FollowUpSurveySubmit, FollowUpTokenStateResponse

router = APIRouter(prefix="/follow-up", tags=["follow-up"])


def _audit(db: OrmSession, session_id: uuid.UUID, event_type: str, payload: dict | None = None) -> None:
    """写入一条随访相关审计事件。"""
    db.add(AuditEvent(session_id=session_id, event_type=event_type, payload=payload))


@router.get("/{token}", response_model=FollowUpTokenStateResponse)
def get_followup_form_state(token: str, db: OrmSession = Depends(get_db)) -> FollowUpTokenStateResponse:
    """根据 token 判断随访表是否可填、是否已提交。"""
    fu = db.scalars(select(SessionFollowup).where(SessionFollowup.followup_token == token)).one_or_none()
    if fu is None:
        raise HTTPException(status_code=404, detail="Invalid follow-up link.")
    sess = db.get(SessionRecord, fu.session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    already = fu.submitted_at is not None
    can = (
        sess.status == "completed"
        and not already
    )
    return FollowUpTokenStateResponse(
        can_submit=can,
        already_submitted=already,
        schema_version=SURVEY_SCHEMA_FOLLOWUP_7D,
    )


@router.post("/{token}", response_model=FollowUpSubmitOkResponse)
def submit_followup(
    token: str,
    body: FollowUpSurveySubmit,
    db: OrmSession = Depends(get_db),
) -> FollowUpSubmitOkResponse:
    """提交 7 天随访问卷正文（需主研究已完成且未重复提交）。"""
    fu = db.scalars(select(SessionFollowup).where(SessionFollowup.followup_token == token)).one_or_none()
    if fu is None:
        raise HTTPException(status_code=404, detail="Invalid follow-up link.")
    if fu.submitted_at is not None:
        raise HTTPException(status_code=409, detail="Follow-up survey was already submitted.")
    sess = db.get(SessionRecord, fu.session_id)
    if sess is None or sess.status != "completed":
        raise HTTPException(status_code=400, detail="Main study not completed; cannot submit follow-up.")

    fu.response_json = body.model_dump()
    fu.submitted_at = datetime.now(timezone.utc)
    fu.response_schema_version = SURVEY_SCHEMA_FOLLOWUP_7D
    _audit(db, fu.session_id, "followup_submitted", {"schema_version": SURVEY_SCHEMA_FOLLOWUP_7D})
    db.commit()
    return FollowUpSubmitOkResponse()
