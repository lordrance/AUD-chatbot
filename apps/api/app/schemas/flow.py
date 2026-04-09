# 模块中文说明：同意、资格、基线、会话状态、聊天与后测的 Pydantic 模型（OpenAPI 契约）。
"""同意、资格、基线、会话状态、聊天回合与后测等 API 的请求/响应模型。"""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ConsentSubmit(BaseModel):
    """提交知情同意：须勾选接受，且版本号与服务器一致。"""

    consent_accepted: Literal[True]
    consent_document_version: str = Field(min_length=1, max_length=64)


class EligibilitySubmit(BaseModel):
    """资格筛查：AUDIT-C、减量意愿 + PDF 入组前安全筛查（任一危机项为真则不合格）。"""

    age_years: int = Field(ge=0, le=120, description="Age in years; eligibility decided server-side")
    sex_at_birth: Literal["male", "female", "other"]
    audit_c_frequency: int = Field(ge=0, le=4, description="AUDIT-C Q1 frequency 0–4")
    audit_c_typical_quantity: int = Field(ge=0, le=4, description="AUDIT-C Q2 typical quantity 0–4")
    audit_c_binge: int = Field(ge=0, le=4, description="AUDIT-C Q3 binge frequency 0–4")
    wants_to_reduce_drinking: bool = Field(description="Wants to reduce drinking (inclusion criterion)")
    crisis_seeking_emergency_help_now: bool = Field(
        default=False,
        description="True if participant needs emergency help right now (exclusion).",
    )
    crisis_unable_to_complete_severe_distress: bool = Field(
        default=False,
        description="True if too unwell to complete the session (exclusion).",
    )
    crisis_needs_immediate_medical_or_clinical: bool = Field(
        default=False,
        description="True if needs immediate medical/crisis services (exclusion).",
    )


class BaselineSubmit(BaseModel):
    """基线问卷：饮酒、准备度、重要性、人口学简要、AI 使用史、治疗状态等（PDF 扩展）。"""

    typical_drinks_last_week: float = Field(ge=0, le=1000, description="Approx. standard drinks last week")
    readiness_to_change_1_10: int = Field(ge=1, le=10, description="Readiness to change 1–10")
    importance_to_reduce_0_10: int = Field(ge=0, le=10, description="How important is cutting down now (0–10)")
    prior_chatbot_or_ai_use: Literal["never", "rarely", "sometimes", "often"] = Field(
        description="Prior use of chatbots/AI for health or habits"
    )
    in_treatment_for_aud_or_mental_health: bool = Field(
        description="Currently in any treatment for alcohol use or mental health"
    )
    treatment_notes: str | None = Field(default=None, max_length=500)
    education_level: Literal["less_than_hs", "hs_ged", "some_college", "college_grad", "grad_prof", "prefer_not"] = Field(
        description="Highest education (brief demographics)"
    )
    employment_status: Literal["employed", "student", "unemployed", "retired", "other", "prefer_not"] = Field(
        description="Current employment status"
    )
    primary_concern_short: str | None = Field(default=None, max_length=500)

    @field_validator("primary_concern_short", "treatment_notes")
    @classmethod
    def strip_optional(cls, v: str | None) -> str | None:
        """可选字段去空白；全空白则视为未填。"""
        if v is None:
            return None
        s = v.strip()
        return s or None


class EligibilityResult(BaseModel):
    """服务端资格判定结果（供 eligibility 服务返回）。"""

    passed: bool
    audit_c_total: int
    audit_c_threshold: int
    reasons: list[str] = Field(default_factory=list)


class ConsentOkResponse(BaseModel):
    """同意提交成功响应。"""

    ok: Literal[True] = True
    status: str
    consent_document_version: str


class EligibilityOkResponse(BaseModel):
    """筛查通过响应。"""

    ok: Literal[True] = True
    status: str
    audit_c_total: int
    passed: Literal[True] = True


class EligibilityFailResponse(BaseModel):
    """筛查未通过响应（含原因码与展示文案）。"""

    ok: Literal[False] = False
    status: Literal["ineligible"] = "ineligible"
    passed: Literal[False] = False
    audit_c_total: int
    reasons: list[str]
    message: str


class BaselineOkResponse(BaseModel):
    """基线提交成功响应。"""

    ok: Literal[True] = True
    status: str


class RandomizeOkResponse(BaseModel):
    """随机分组结果（含臂与是否此前已分配）。"""

    ok: Literal[True] = True
    status: str
    arm: str
    already_assigned: bool = False


class SessionStateResponse(BaseModel):
    """GET state 返回的会话全景（阶段、槽位、安全、摘要等）。"""

    session_id: UUID
    status: str
    arm: str | None
    fsm_stage: int = Field(
        description="Chat FSM 0–4; may stay 0 before chat—use chat_stage together.",
    )
    chat_stage: int | None = Field(
        default=None,
        description="None if chat not started; else current chat stage 0–4.",
    )
    current_stage: int | None = Field(
        default=None,
        description="Frozen contract field: same as chat_stage.",
    )
    chat_enabled: bool
    chat_open: bool = False
    chat_completed: bool = False
    post_survey_unlocked: bool = False
    next_step: str
    expected_consent_version: str
    ineligible_reason: str | None = None
    user_turns_in_current_stage: int | None = None
    current_substate: str | None = None
    slot_json: dict[str, Any] | None = None
    rolling_summary: str | None = None
    prompt_version: str | None = Field(
        default=None,
        description="Frozen prompt bundle ref, e.g. safechat-aud@0.1; set at randomization.",
    )
    dropout_stage: str | None = Field(default=None, description="Dropout / abort code if applicable.")
    safety_max_severity: int = Field(default=0, ge=0, le=3, description="Max rule-based severity 0–3 this session.")
    safety_last_routing_action: str | None = Field(default=None, description="Last safety routing action.")
    safety_show_resources_prompt: bool = Field(
        default=False,
        description="Frontend may prompt participant to open Help & resources while flow continues.",
    )
    safety_chat_permitted: bool = Field(
        default=True,
        description="Whether chat may continue (false if ended by safety policy).",
    )
    chat_summary: dict[str, Any] | None = Field(
        default=None,
        description="Structured summary at chat end (export); see chat_summary_json.",
    )
    chat_section_1_to_4: int | None = Field(
        default=None,
        ge=1,
        le=4,
        description="Chat-only progress 1/4–4/4: FSM0→1, FSM1→2, FSM2→3, FSM3–4→4; Stage1 feedback pause shows 2/4.",
    )
    max_user_turns_current_stage: int | None = Field(
        default=None,
        description="Server cap for user turns in current chat stage; null if N/A.",
    )
    stage1_feedback_card: dict[str, Any] | None = Field(
        default=None,
        description="When status is stage1_feedback_pending: baseline drinks + Stage1 slot recap.",
    )
    study_target_assistant_turns_min: int | None = Field(
        default=None,
        description="Protocol target min assistant turns (answer2.pdf reporting).",
    )
    study_target_assistant_turns_max: int | None = Field(
        default=None,
        description="Protocol target max assistant turns (answer2.pdf reporting).",
    )
    llm_api_type_label: str | None = Field(
        default=None,
        description="LLM transport label for audit (e.g. chat_completions).",
    )
    assistant_turns_so_far: int | None = Field(
        default=None,
        ge=0,
        description="Count of assistant chat_turn rows so far (vs study_target_assistant_turns_*).",
    )
    model_id: str | None = None
    api_type: str | None = None
    store_flag: bool | None = None
    global_prompt_version: str | None = None
    style_prompt_version: str | None = None
    stage_prompt_version: str | None = None
    strategy_library_version: str | None = None
    frontend_build: str | None = None
    backend_build: str | None = None


class PostSurveySubmit(BaseModel):
    """后测问卷（schema v4）：WAI-TECH-SF 12 项（1–7）、过程量表、操纵检验与两道开放题。"""

    wai_tech_sf_item_01: int = Field(ge=1, le=7, description="WAI-TECH-SF item 1")
    wai_tech_sf_item_02: int = Field(ge=1, le=7)
    wai_tech_sf_item_03: int = Field(ge=1, le=7)
    wai_tech_sf_item_04: int = Field(ge=1, le=7)
    wai_tech_sf_item_05: int = Field(ge=1, le=7)
    wai_tech_sf_item_06: int = Field(ge=1, le=7)
    wai_tech_sf_item_07: int = Field(ge=1, le=7)
    wai_tech_sf_item_08: int = Field(ge=1, le=7)
    wai_tech_sf_item_09: int = Field(ge=1, le=7)
    wai_tech_sf_item_10: int = Field(ge=1, le=7)
    wai_tech_sf_item_11: int = Field(ge=1, le=7)
    wai_tech_sf_item_12: int = Field(ge=1, le=7)
    trust_1_5: int = Field(ge=1, le=5)
    helpfulness_1_5: int = Field(ge=1, le=5)
    disclosure_comfort_1_5: int = Field(ge=1, le=5)
    change_intention_1_5: int = Field(ge=1, le=5)
    manipulation_felt_warm_1_5: int = Field(ge=1, le=5)
    manipulation_felt_professional_1_5: int = Field(ge=1, le=5)
    manipulation_felt_practical_actionable_1_5: int = Field(
        ge=1,
        le=5,
        description="Higher = more practical/problem-solving and actionable (manipulation check for condition B)",
    )
    manipulation_understood_feelings_1_5: int = Field(ge=1, le=5)
    manipulation_felt_repetitive_1_5: int = Field(ge=1, le=5, description="Higher = more repetitive/scripted")
    manipulation_felt_personal_tailored_1_5: int = Field(ge=1, le=5)
    open_most_helpful: str = Field(min_length=1, max_length=2000)
    open_unnatural_or_uncomfortable: str = Field(min_length=1, max_length=2000)


class PostSurveyOkResponse(BaseModel):
    """后测提交成功响应。"""

    ok: Literal[True] = True
    status: str


class ChatTurnResponse(BaseModel):
    """单轮聊天 API 返回：助手正文、是否 stub、阶段与安全路由等。"""

    assistant_text: str
    stub: bool = Field(
        default=True,
        description="True: YAML stub or LLM parse/call fallback; False: validated structured LLM output.",
    )
    stage_after: int
    exchange_index: int
    status_after: str
    chat_closed: bool = False
    stage1_feedback_required: bool = Field(
        default=False,
        description="True: participant should open Stage 1 feedback screen before continuing chat.",
    )
    prompt_version: str | None = None
    safety_severity_this_turn: int = Field(default=0, ge=0, le=3)
    safety_routing_action: str = Field(default="CONTINUE")
    safety_resources_suggested: bool = False


class Stage1FeedbackContinueResponse(BaseModel):
    """确认 Stage1 反馈卡后继续聊天：返回 Stage2 首条助手文案。"""

    ok: Literal[True] = True
    assistant_text: str
    stub: bool = True
    status_after: str
    exchange_index: int
    prompt_version: str | None = None


class ConsentDocumentResponse(BaseModel):
    """公开 GET /consent-document 返回体（版本号 + Markdown 正文）。"""

    consent_document_version: str
    format: Literal["markdown"] = "markdown"
    body: str
