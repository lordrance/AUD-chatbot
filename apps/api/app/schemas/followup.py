# 模块中文说明：7 天随访 opt-in 与 token 公开提交的请求/响应模型。
"""7 天随访：opt-in 请求体、token 状态与公开提交问卷（无邮件自动化）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class FollowUpOptInBody(BaseModel):
    """主流程完成后登记随访联系方式（须至少邮箱或电话之一）。"""

    opted_in: Literal[True]
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def require_contact(self) -> FollowUpOptInBody:
        """校验至少填写一种联系方式。"""
        if not (self.contact_email or "").strip() and not (self.contact_phone or "").strip():
            raise ValueError("Please provide at least one contact method (email or phone).")
        return self


class FollowUpOptInOkResponse(BaseModel):
    """随访登记成功：返回 token 与公开路径片段。"""

    ok: Literal[True] = True
    followup_token: str
    followup_public_path: str


class FollowUpTokenStateResponse(BaseModel):
    """公开 GET 随访链接时的可填状态与 schema 版本。"""

    can_submit: bool
    already_submitted: bool
    schema_version: str


class FollowUpSurveySubmit(BaseModel):
    """7 天极简随访问卷字段。"""

    drinking_days_last_7: int = Field(ge=0, le=7)
    heavy_drinking_days_last_7: int = Field(ge=0, le=7)
    used_plan: Literal["yes", "no", "somewhat"]
    intention_confidence_reduce_1_10: int = Field(ge=1, le=10, description="Intention/confidence to reduce drinking 1–10")
    willing_to_use_again_1_5: int = Field(ge=1, le=5)

    @model_validator(mode="after")
    def heavy_le_drinking(self) -> FollowUpSurveySubmit:
        """大量饮酒天数不得大于总饮酒天数。"""
        if self.heavy_drinking_days_last_7 > self.drinking_days_last_7:
            raise ValueError("Heavy drinking days cannot exceed total drinking days.")
        return self


class FollowUpSubmitOkResponse(BaseModel):
    """随访问卷提交成功占位响应。"""

    ok: Literal[True] = True
