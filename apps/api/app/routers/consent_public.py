"""公开同意书全文接口（无需会话 token）。"""

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.schemas.flow import ConsentDocumentResponse
from app.services.consent_document import load_consent_markdown

router = APIRouter(tags=["consent"])


@router.get("/consent-document", response_model=ConsentDocumentResponse)
def get_consent_document() -> ConsentDocumentResponse:
    """返回当前配置的同意书 Markdown 正文与版本号。"""
    try:
        body = load_consent_markdown(settings.consent_document_version)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="consent document body missing on server")
    return ConsentDocumentResponse(
        consent_document_version=settings.consent_document_version,
        body=body,
    )
