"""FastAPI 依赖：解析 Bearer token 并加载当前会话行。"""

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.session import SessionRecord


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    """从 Authorization 头提取 Bearer token；格式不对或为空则 401。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header (expected Bearer token).",
        )
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty bearer token.")
    return token


def get_current_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    token: str = Depends(get_bearer_token),
) -> SessionRecord:
    """根据路径中的 session_id 与 Bearer token 校验并返回会话 ORM 行；404/403 时抛 HTTP 异常。"""
    row = db.scalars(select(SessionRecord).where(SessionRecord.id == session_id)).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    if row.session_token != token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid session token.")
    return row
