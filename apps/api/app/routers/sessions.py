"""
会话 REST 路由：同意、筛查、基线、随机分组、聊天轮次、后测、随访 opt-in；
含聊前/聊中安全闸、审计与可选 LLM。
"""
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import settings
from app.constants import (
    LLM_API_TYPE_LABEL,
    STUDY_TARGET_ASSISTANT_TURNS_MAX,
    STUDY_TARGET_ASSISTANT_TURNS_MIN,
    SURVEY_SCHEMA_BASELINE,
    SURVEY_SCHEMA_CONSENT,
    SURVEY_SCHEMA_ELIGIBILITY,
    SURVEY_SCHEMA_POST,
)
from app.database import get_db
from app.dependencies import get_current_session
from app.models.audit_event import AuditEvent
from app.models.chat_turn import ChatTurn
from app.models.llm_call import LlmCall
from app.models.session import SessionRecord
from app.models.session_followup import SessionFollowup
from app.models.stage_state_event import StageStateEvent
from app.models.survey_response import SurveyResponse
from app.schemas.followup import FollowUpOptInBody, FollowUpOptInOkResponse
from app.schemas.flow import (
    BaselineOkResponse,
    BaselineSubmit,
    ChatTurnResponse,
    ConsentOkResponse,
    ConsentSubmit,
    EligibilityFailResponse,
    EligibilityOkResponse,
    EligibilitySubmit,
    PostSurveyOkResponse,
    PostSurveySubmit,
    RandomizeOkResponse,
    SessionStateResponse,
    Stage1FeedbackContinueResponse,
)
from app.services.arm_styles import pick_random_arm
from app.services.chat_summary import persist_chat_summary
from app.services.strategy_library import strategies_payload_for_turn
from app.services.chat_fsm import (
    STAGE_3_SHRINK_SLOTS,
    MAX_CHAT_STAGE,
    first_missing_slot,
    initial_current_substate,
    max_user_turns_for_stage,
    next_stage_after_completion,
    parse_rating_0_10,
    pad_incomplete_stage_with_cap_marker,
    qualified_slot_key,
    required_slots_for_stage,
    slot_value_satisfied,
    stage_slots_complete,
    total_required_slots_count,
)
from app.services.chat_llm_compose import build_turn_messages
from app.services.chat_stub_content import build_assistant_slot_stub, load_strategies_placeholder
from app.services.eligibility import evaluate_eligibility
from app.services.llm_client import (
    call_chat_turn_structured,
    effective_llm_model,
    llm_endpoint_hang_risk,
    llm_is_configured,
)
from app.services.prompt_registry import load_bundle, resolve_version_ref_for_session
from app.services.flow_messages import format_ineligible_message
from app.services.safety_routing import (
    ASSISTANT_EMERGENCY_STOP,
    ASSISTANT_SAFE_END_CHAT,
    RoutingAction,
    append_safety_flag,
    merge_session_severity,
    pre_chat_text_from_surveys,
    scan_user_text,
    severity_to_action,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _touch_activity(row: SessionRecord) -> None:
    """刷新会话最近活动时间戳。"""
    row.last_activity_at = datetime.now(timezone.utc)


def _record_audit(db: OrmSession, session_id: uuid.UUID, event_type: str, payload: dict[str, Any] | None = None) -> None:
    """追加一条审计事件（未 commit）。"""
    db.add(AuditEvent(session_id=session_id, event_type=event_type, payload=payload))


def _next_step(status_value: str) -> str:
    """将内部 status 映射为前端流程用的 next_step 字符串。"""
    mapping = {
        "consent_pending": "consent",
        "eligibility_pending": "eligibility",
        "baseline_pending": "baseline_survey",
        "pending_randomization": "randomize",
        "chat_ready": "chat",
        "chat_active": "chat",
        "stage1_feedback_pending": "stage1_feedback",
        "post_survey_pending": "post_survey",
        "completed": "done",
        "ineligible": "end",
        "abandoned": "end",
    }
    return mapping.get(status_value, "unknown")


def _survey_exists(db: OrmSession, session_id: uuid.UUID, instrument: str) -> bool:
    """该会话是否已提交过指定 instrument 的问卷。"""
    q = select(SurveyResponse.id).where(
        SurveyResponse.session_id == session_id,
        SurveyResponse.instrument == instrument,
    )
    return db.scalars(q).one_or_none() is not None


def _ineligible_summary_for_state(row: SessionRecord) -> str | None:
    """若会话为不合格状态，返回拼好的参与者可读说明；否则 None。"""
    if row.status != "ineligible" or not row.ineligible_reasons:
        return None
    codes = row.ineligible_reasons.get("codes")
    if not isinstance(codes, list):
        return None
    str_codes = [str(c) for c in codes]
    return format_ineligible_message(str_codes)


def _chat_stage_for_api(row: SessionRecord) -> int | None:
    """对外展示的聊天阶段号；未进入或已结束聊天时规则见内部分支。"""
    if row.status in ("chat_ready", "chat_active", "stage1_feedback_pending", "post_survey_pending"):
        return row.fsm_stage
    if row.status == "completed":
        return 4
    return None


def _chat_section_1_to_4(row: SessionRecord) -> int | None:
    """聊天子进度 1/4–4/4：0→1、1→2、2→3、3 与 4→4；Stage1 反馈卡暂停时仍显示 2/4。"""
    if not row.arm:
        return None
    if row.status == "stage1_feedback_pending":
        return 2
    if row.status in ("chat_ready", "chat_active"):
        fs = row.fsm_stage
        if fs <= 0:
            return 1
        if fs == 1:
            return 2
        if fs == 2:
            return 3
        return 4
    if row.status in ("post_survey_pending", "completed"):
        return 4
    return None


def _max_user_turns_current_stage(row: SessionRecord) -> int | None:
    if row.status not in ("chat_ready", "chat_active"):
        return None
    return max_user_turns_for_stage(row.fsm_stage)


def _stage1_feedback_card_payload(db: OrmSession, row: SessionRecord) -> dict[str, Any] | None:
    if row.status != "stage1_feedback_pending":
        return None
    q = select(SurveyResponse).where(
        SurveyResponse.session_id == row.id,
        SurveyResponse.instrument == "baseline",
    )
    br = db.scalars(q).first()
    drinks: Any = None
    if br and isinstance(br.answers, dict):
        drinks = br.answers.get("typical_drinks_last_week")
    slots = dict(row.slot_json or {})
    keys = (
        "1:recent_drinking_pattern",
        "1:most_concerning_episode",
        "1:top_reason_to_cut_down",
        "1:importance_0_10",
        "1:confidence_0_10",
    )
    stage1 = {k.split(":", 1)[1]: slots.get(k) for k in keys}
    return {
        "typical_drinks_last_week_baseline": drinks,
        "stage1_slots": stage1,
    }


def _assistant_turns_count(db: OrmSession, session_id: uuid.UUID) -> int:
    """已落库的助手消息条数（用于协议 12–16 bot turns 对照与前端展示）。"""
    q = select(func.count()).select_from(ChatTurn).where(
        ChatTurn.session_id == session_id,
        ChatTurn.role == "assistant",
    )
    n = db.scalar(q)
    return int(n or 0)


def _text_word_count(text: str | None) -> int:
    t = (text or "").strip()
    if not t:
        return 0
    return len([w for w in t.split() if w])


def _slot_completion_percent(slots: dict[str, Any]) -> int:
    required = 0
    filled = 0
    for sg in range(0, MAX_CHAT_STAGE + 1):
        for sk in required_slots_for_stage(sg):
            required += 1
            if slot_value_satisfied(sg, sk, slots.get(qualified_slot_key(sg, sk))):
                filled += 1
    # Stage 3 confidence < 7 时，追加两项 shrink 槽位到分母/分子。
    conf = parse_rating_0_10(slots.get(qualified_slot_key(3, "final_confidence_0_10")))
    if conf is not None and conf < 7:
        for sk in STAGE_3_SHRINK_SLOTS:
            required += 1
            if slot_value_satisfied(3, sk, slots.get(qualified_slot_key(3, sk))):
                filled += 1
    if required <= 0:
        return 0
    return max(0, min(100, int(round((filled / required) * 100))))


def _dropout_reason_for_state(row: SessionRecord) -> str | None:
    if row.status == "abandoned":
        return "safety" if row.safety_policy_chat_ended else "user_exit"
    if row.status == "ineligible":
        return "eligibility"
    return None


def _update_session_meta_metrics(db: OrmSession, row: SessionRecord) -> None:
    q = select(ChatTurn.role, ChatTurn.text).where(ChatTurn.session_id == row.id)
    turns = list(db.execute(q).all())
    total_turns = len(turns)
    total_user_words = 0
    total_bot_words = 0
    for role, text in turns:
        wc = _text_word_count(text)
        if role == "assistant":
            total_bot_words += wc
        elif role == "user":
            total_user_words += wc

    start_at = row.chat_started_at or row.created_at
    end_at = row.chat_completed_at or (datetime.now(timezone.utc) if row.status in ("completed", "abandoned") else None)
    total_duration_sec = int((end_at - start_at).total_seconds()) if (start_at and end_at) else None
    slots = dict(row.slot_json or {})
    row.session_meta_json = {
        **dict(row.session_meta_json or {}),
        "participant_id": str(row.id),
        "assigned_condition": row.arm,
        "started_at": start_at.isoformat() if start_at else None,
        "ended_at": end_at.isoformat() if end_at else None,
        "completed": row.status == "completed",
        "dropout_stage": row.dropout_stage,
        "dropout_reason": _dropout_reason_for_state(row),
        "total_duration_sec": total_duration_sec,
        "total_turns": total_turns,
        "total_user_words": total_user_words,
        "total_bot_words": total_bot_words,
        "completion_percent": _slot_completion_percent(slots),
        "required_slot_count_base": total_required_slots_count(),
    }


def _latest_llm_api_type(db: OrmSession, session_id: uuid.UUID) -> str | None:
    q = (
        select(LlmCall.api_type)
        .where(LlmCall.session_id == session_id)
        .order_by(LlmCall.created_at.desc())
        .limit(1)
    )
    return db.scalar(q)


def _force_fill_until_close(slots: dict[str, Any], start_stage: int) -> None:
    """为 turn budget 强制收尾：从当前阶段起补齐所有剩余必填槽。"""
    for sg in range(start_stage, MAX_CHAT_STAGE + 1):
        pad_incomplete_stage_with_cap_marker(sg, slots)


def _append_stage_state_event(
    db: OrmSession,
    row: SessionRecord,
    *,
    turn_index: int,
    current_stage: int,
    slots: dict[str, Any],
    stage_complete: bool,
    reason_for_transition: str | None,
    selected_strategy_ids: list[str] | None = None,
) -> None:
    """记录阶段状态快照（每轮至少一条，便于论文过程分析）。"""
    db.add(
        StageStateEvent(
            session_id=row.id,
            turn_index=turn_index,
            current_stage=current_stage,
            slots_json=dict(slots),
            stage_complete=stage_complete,
            reason_for_transition=reason_for_transition,
            importance_score=parse_rating_0_10(slots.get(qualified_slot_key(1, "importance_0_10"))),
            confidence_score=parse_rating_0_10(slots.get(qualified_slot_key(3, "final_confidence_0_10"))),
            selected_strategy_ids=list(selected_strategy_ids or []),
            if_then_plan=str(slots.get(qualified_slot_key(3, "if_then_plan")) or "").strip() or None,
            rolling_summary=(row.rolling_summary or "")[-4000:] or None,
        )
    )


def _heuristic_style_fidelity(assistant_text: str) -> dict[str, Any]:
    """规则型 style fidelity 标签（最小可用）：先启发式，后续可人工复核。不采集姓名，故不使用参与者姓名匹配。"""
    txt = (assistant_text or "").strip()
    low = txt.lower()
    num_questions = txt.count("?")
    has_reflection = any(k in low for k in ("it sounds", "it seems", "you mentioned", "you said"))
    has_affirmation = any(k in low for k in ("good job", "well done", "thanks for sharing", "that makes sense"))
    has_emotion_label = any(k in low for k in ("stressed", "anxious", "frustrated", "sad", "bored", "relaxed"))
    has_summary = any(k in low for k in ("to summarize", "in short", "you said", "summary"))
    has_practical_suggestion = any(k in low for k in ("if", "then", "plan", "step", "try", "backup"))
    has_autonomy_support = any(k in low for k in ("you can choose", "if you want", "when you're ready", "your choice"))
    uses_name = False
    directiveness_score = min(5, max(1, 1 + int(any(k in low for k in ("should", "must", "need to", "do this")))))
    warmth_score = min(5, max(1, 1 + int(has_reflection) + int(has_affirmation) + int(has_autonomy_support)))
    return {
        "num_questions": num_questions,
        "has_reflection": has_reflection,
        "has_affirmation": has_affirmation,
        "has_emotion_label": has_emotion_label,
        "has_summary": has_summary,
        "has_practical_suggestion": has_practical_suggestion,
        "has_autonomy_support": has_autonomy_support,
        "uses_participant_name": uses_name,
        "directiveness_score": directiveness_score,
        "warmth_score": warmth_score,
    }


def _slot_snapshot_for_api(row: SessionRecord) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """返回 (current_substate, slot_json, rolling_summary 截断) 供 state 接口；不适用时全 None。"""
    if row.status not in (
        "chat_ready",
        "chat_active",
        "stage1_feedback_pending",
        "post_survey_pending",
        "completed",
    ) or not row.arm:
        return None, None, None
    summary = row.rolling_summary or ""
    if len(summary) > 8000:
        summary = summary[-8000:]
    return row.current_substate, dict(row.slot_json or {}), summary


def _state_response(db: OrmSession, row: SessionRecord) -> SessionStateResponse:
    """由 ORM 会话行组装 GET state 的响应体。"""
    cs = _chat_stage_for_api(row)
    chat_open = row.status in ("chat_ready", "chat_active")
    chat_completed = row.chat_completed_at is not None or row.status in ("post_survey_pending", "completed")
    post_unlocked = row.status == "post_survey_pending"
    if row.status in ("chat_ready", "chat_active"):
        ut: int | None = row.chat_user_turns_in_stage
    else:
        ut = None
    fsm_display = cs if cs is not None else row.fsm_stage
    sub, slots, roll = _slot_snapshot_for_api(row)
    sev = int(row.safety_max_severity or 0)
    safety_show = sev >= 1 and row.status not in ("abandoned", "completed", "ineligible")
    safety_chat_ok = row.status in ("chat_ready", "chat_active")
    s1_card = _stage1_feedback_card_payload(db, row)
    meta = dict(row.session_meta_json or {})
    turn_tgt_min = STUDY_TARGET_ASSISTANT_TURNS_MIN if row.arm else None
    turn_tgt_max = STUDY_TARGET_ASSISTANT_TURNS_MAX if row.arm else None
    llm_lbl = (_latest_llm_api_type(db, row.id) or LLM_API_TYPE_LABEL) if row.arm else None
    asst_turns = (
        _assistant_turns_count(db, row.id)
        if row.arm and row.status in ("chat_ready", "chat_active", "stage1_feedback_pending")
        else None
    )
    return SessionStateResponse(
        session_id=row.id,
        status=row.status,
        arm=row.arm,
        fsm_stage=fsm_display,
        chat_stage=cs,
        current_stage=cs,
        chat_enabled=chat_open,
        chat_open=chat_open,
        chat_completed=chat_completed,
        post_survey_unlocked=post_unlocked,
        next_step=_next_step(row.status),
        expected_consent_version=settings.consent_document_version,
        ineligible_reason=_ineligible_summary_for_state(row),
        user_turns_in_current_stage=ut,
        current_substate=sub,
        slot_json=slots,
        rolling_summary=roll,
        prompt_version=row.prompt_bundle_version,
        dropout_stage=row.dropout_stage,
        safety_max_severity=sev,
        safety_last_routing_action=row.safety_last_routing_action,
        safety_show_resources_prompt=safety_show,
        safety_chat_permitted=safety_chat_ok,
        chat_summary=dict(row.chat_summary_json) if isinstance(row.chat_summary_json, dict) else None,
        chat_section_1_to_4=_chat_section_1_to_4(row),
        max_user_turns_current_stage=_max_user_turns_current_stage(row),
        stage1_feedback_card=s1_card,
        study_target_assistant_turns_min=turn_tgt_min,
        study_target_assistant_turns_max=turn_tgt_max,
        llm_api_type_label=llm_lbl,
        assistant_turns_so_far=asst_turns,
        model_id=(str(meta.get("model_id")) if meta.get("model_id") is not None else None),
        api_type=(str(meta.get("api_type")) if meta.get("api_type") is not None else None),
        store_flag=(bool(meta.get("store_flag")) if meta.get("store_flag") is not None else None),
        global_prompt_version=(str(meta.get("global_prompt_version")) if meta.get("global_prompt_version") is not None else None),
        style_prompt_version=(str(meta.get("style_prompt_version")) if meta.get("style_prompt_version") is not None else None),
        stage_prompt_version=(str(meta.get("stage_prompt_version")) if meta.get("stage_prompt_version") is not None else None),
        strategy_library_version=(
            str(meta.get("strategy_library_version")) if meta.get("strategy_library_version") is not None else None
        ),
        frontend_build=(str(meta.get("frontend_build")) if meta.get("frontend_build") is not None else None),
        backend_build=(str(meta.get("backend_build")) if meta.get("backend_build") is not None else None),
    )


class SessionCreatedResponse(BaseModel):
    """POST /sessions 创建成功时返回的 id 与 token。"""

    session_id: uuid.UUID
    session_token: str


class SessionCreateBody(BaseModel):
    """创建会话时可选的参与者/环境元数据。"""

    recruitment_source: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)
    device_type: str | None = Field(default=None, max_length=32)
    browser: str | None = Field(default=None, max_length=64)


class ChatTurnBody(BaseModel):
    """单轮聊天请求体：用户输入文本。"""

    text: str = Field(min_length=1, max_length=8000)
    timestamp_client_send: datetime | None = None


class UiEventBody(BaseModel):
    """前端 UI 遥测（写入审计事件，供参与度与流失分析）。"""

    event_type: str = Field(min_length=1, max_length=64)
    event_value: str | None = Field(default=None, max_length=500)
    turn_index: int | None = None


class UiEventOkResponse(BaseModel):
    ok: Literal[True] = True


def _detect_device_type(user_agent: str) -> str | None:
    ua = (user_agent or "").lower()
    if not ua:
        return None
    if any(k in ua for k in ("iphone", "android", "mobile")):
        return "mobile"
    if any(k in ua for k in ("ipad", "tablet")):
        return "tablet"
    return "desktop"


def _detect_browser(user_agent: str) -> str | None:
    ua = (user_agent or "").lower()
    if not ua:
        return None
    if "edg/" in ua:
        return "edge"
    if "chrome/" in ua and "edg/" not in ua:
        return "chrome"
    if "firefox/" in ua:
        return "firefox"
    if "safari/" in ua and "chrome/" not in ua:
        return "safari"
    return "other"


def _recent_turns_transcript(db: OrmSession, session_id: uuid.UUID, limit: int = 14) -> str:
    """取最近若干条 chat_turns 拼成「role: text」多行文本，供 LLM 上下文。"""
    q = (
        select(ChatTurn)
        .where(ChatTurn.session_id == session_id)
        .order_by(ChatTurn.turn_index.desc())
        .limit(limit)
    )
    rows = list(db.scalars(q).all())
    rows.reverse()
    lines: list[str] = []
    for r in rows:
        lines.append(f"{r.role}: {(r.text or '')[:800]}")
    return "\n".join(lines)


@router.post("", response_model=SessionCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    request: Request,
    body: SessionCreateBody | None = None,
    db: OrmSession = Depends(get_db),
) -> SessionCreatedResponse:
    """创建新会话并返回 id 与 session_token（后续 Bearer）。"""
    token = secrets.token_urlsafe(32)
    ua = request.headers.get("user-agent", "") if request else ""
    timezone_header = request.headers.get("x-timezone") if request else None
    b = body or SessionCreateBody()
    row = SessionRecord(
        session_token=token,
        status="consent_pending",
        fsm_stage=0,
        slot_json={},
        rolling_summary="",
        current_substate=None,
        session_meta_json={
            "participant_id": None,  # flush 后回填
            "recruitment_source": b.recruitment_source,
            "language": b.language,
            "timezone": b.timezone or timezone_header,
            "device_type": b.device_type or _detect_device_type(ua),
            "browser": b.browser or _detect_browser(ua),
            "randomization_block": settings.randomization_mode,
        },
    )
    db.add(row)
    db.flush()
    row.session_meta_json = {
        **dict(row.session_meta_json or {}),
        "participant_id": str(row.id),
    }
    _record_audit(db, row.id, "session_created", {"session_id": str(row.id)})
    db.commit()
    db.refresh(row)
    return SessionCreatedResponse(session_id=row.id, session_token=token)


@router.get("/{session_id}/state", response_model=SessionStateResponse)
def get_state(
    row: SessionRecord = Depends(get_current_session),
    db: OrmSession = Depends(get_db),
) -> SessionStateResponse:
    """返回当前会话完整状态（含聊天阶段、槽位、安全字段、摘要等）。"""
    _touch_activity(row)
    db.add(row)
    db.commit()
    return _state_response(db, row)


@router.post("/{session_id}/instrument/ui-event", response_model=UiEventOkResponse)
def post_ui_event(
    body: UiEventBody,
    row: SessionRecord = Depends(get_current_session),
    db: OrmSession = Depends(get_db),
) -> UiEventOkResponse:
    """记录 UI 事件（focus、send、quick_reply、blur 等）；落 audit_events 便于导出分析。"""
    _record_audit(
        db,
        row.id,
        "ui_event",
        {
            "event_type": body.event_type,
            "event_value": body.event_value,
            "turn_index": body.turn_index,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "fsm_stage": row.fsm_stage,
        },
    )
    _touch_activity(row)
    db.commit()
    return UiEventOkResponse(ok=True)


@router.post("/{session_id}/consent", response_model=ConsentOkResponse)
def post_consent(
    body: ConsentSubmit,
    row: SessionRecord = Depends(get_current_session),
    db: OrmSession = Depends(get_db),
) -> ConsentOkResponse:
    """提交知情同意并写入 survey_responses，状态进入资格待填。"""
    if row.status != "consent_pending":
        raise HTTPException(status_code=400, detail=f"Consent cannot be submitted in status: {row.status}")
    if _survey_exists(db, row.id, "consent"):
        raise HTTPException(status_code=409, detail="Consent was already submitted.")
    if body.consent_document_version != settings.consent_document_version:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Consent document version mismatch: client sent {body.consent_document_version!r}, "
                f"server requires {settings.consent_document_version!r}."
            ),
        )

    now = datetime.now(timezone.utc)
    row.consent_at = now
    row.consent_document_version = body.consent_document_version
    row.status = "eligibility_pending"
    _touch_activity(row)

    db.add(
        SurveyResponse(
            session_id=row.id,
            instrument="consent",
            schema_version=SURVEY_SCHEMA_CONSENT,
            answers=body.model_dump(),
        )
    )
    _record_audit(
        db,
        row.id,
        "consent_submitted",
        {"consent_document_version": body.consent_document_version},
    )
    db.commit()

    return ConsentOkResponse(status=row.status, consent_document_version=body.consent_document_version)


@router.post(
    "/{session_id}/eligibility",
    response_model=EligibilityOkResponse | EligibilityFailResponse,
)
def post_eligibility(
    body: EligibilitySubmit,
    row: SessionRecord = Depends(get_current_session),
    db: OrmSession = Depends(get_db),
) -> EligibilityOkResponse | EligibilityFailResponse:
    """提交资格筛查；不通过则标记 ineligible 并返回原因码与说明。"""
    if row.status != "eligibility_pending":
        raise HTTPException(status_code=400, detail=f"Eligibility cannot be submitted in status: {row.status}")
    if _survey_exists(db, row.id, "eligibility"):
        raise HTTPException(status_code=409, detail="Eligibility was already submitted.")

    result = evaluate_eligibility(body)
    answers_payload: dict[str, Any] = {
        **body.model_dump(),
        "computed_audit_c_total": result.audit_c_total,
        "computed_audit_c_threshold": result.audit_c_threshold,
        "passed": result.passed,
    }

    db.add(
        SurveyResponse(
            session_id=row.id,
            instrument="eligibility",
            schema_version=SURVEY_SCHEMA_ELIGIBILITY,
            answers=answers_payload,
        )
    )

    if not result.passed:
        row.status = "ineligible"
        row.ineligible_reasons = {
            "codes": result.reasons,
            "audit_c_total": result.audit_c_total,
            "audit_c_threshold": result.audit_c_threshold,
        }
        _touch_activity(row)
        _record_audit(
            db,
            row.id,
            "eligibility_failed",
            {"reasons": result.reasons, "audit_c_total": result.audit_c_total},
        )
        db.commit()
        return EligibilityFailResponse(
            audit_c_total=result.audit_c_total,
            reasons=result.reasons,
            message=format_ineligible_message(result.reasons),
        )

    row.status = "baseline_pending"
    row.ineligible_reasons = None
    _touch_activity(row)
    _record_audit(
        db,
        row.id,
        "eligibility_passed",
        {"audit_c_total": result.audit_c_total},
    )
    db.commit()
    return EligibilityOkResponse(status=row.status, audit_c_total=result.audit_c_total)


@router.post("/{session_id}/surveys/baseline", response_model=BaselineOkResponse)
def post_baseline(
    body: BaselineSubmit,
    row: SessionRecord = Depends(get_current_session),
    db: OrmSession = Depends(get_db),
) -> BaselineOkResponse:
    """提交基线问卷；对开放关注字段做安全扫描并进入待随机分组。"""
    if row.status != "baseline_pending":
        raise HTTPException(status_code=400, detail=f"Baseline survey cannot be submitted in status: {row.status}")
    if _survey_exists(db, row.id, "baseline"):
        raise HTTPException(status_code=409, detail="Baseline survey was already submitted.")

    row.status = "pending_randomization"
    _touch_activity(row)
    db.add(
        SurveyResponse(
            session_id=row.id,
            instrument="baseline",
            schema_version=SURVEY_SCHEMA_BASELINE,
            answers=body.model_dump(),
        )
    )
    _record_audit(db, row.id, "baseline_survey_submitted", {"schema_version": SURVEY_SCHEMA_BASELINE})

    for field_name, raw in (
        ("primary_concern_short", body.primary_concern_short or ""),
        ("treatment_notes", body.treatment_notes or ""),
    ):
        if not raw.strip():
            continue
        b_scan = scan_user_text(raw)
        row.safety_max_severity = merge_session_severity(row.safety_max_severity, b_scan.severity)
        row.safety_last_routing_action = severity_to_action(b_scan.severity)
        append_safety_flag(
            row,
            {
                "phase": "baseline_field",
                "field": field_name,
                "codes": b_scan.matched_codes,
                "severity": b_scan.severity,
            },
        )
        _record_audit(
            db,
            row.id,
            "safety_scan_baseline",
            {
                "field": field_name,
                "severity": b_scan.severity,
                "codes": b_scan.matched_codes,
                "session_max_after": row.safety_max_severity,
            },
        )

    db.commit()
    return BaselineOkResponse(status=row.status)


def _reset_chat_counters(row: SessionRecord) -> None:
    """随机分组后重置聊天 FSM、槽位与轮次计数。"""
    row.fsm_stage = 0
    row.chat_user_turns_in_stage = 0
    row.chat_started_at = None
    row.chat_completed_at = None
    row.chat_last_turn_index = 0
    row.chat_exchange_index = 0
    row.slot_json = {}
    row.rolling_summary = ""
    row.current_substate = initial_current_substate()


@router.post("/{session_id}/randomize", response_model=RandomizeOkResponse)
def post_randomize(
    row: SessionRecord = Depends(get_current_session),
    db: OrmSession = Depends(get_db),
) -> RandomizeOkResponse:
    """聊前安全闸 + 1:1 随机分配臂；高危可能 403 并废弃会话。"""
    if row.status in ("chat_ready", "chat_active") and row.arm:
        return RandomizeOkResponse(status=row.status, arm=row.arm, already_assigned=True)

    if row.status != "pending_randomization":
        raise HTTPException(status_code=400, detail=f"Randomization cannot run in status: {row.status}")
    if not _survey_exists(db, row.id, "baseline"):
        raise HTTPException(status_code=400, detail="Baseline survey record not found; cannot randomize.")

    pre_blob = pre_chat_text_from_surveys(db, row.id)
    pre_scan = scan_user_text(pre_blob)
    row.safety_max_severity = merge_session_severity(row.safety_max_severity, pre_scan.severity)
    pre_action = severity_to_action(pre_scan.severity)
    row.safety_last_routing_action = pre_action
    append_safety_flag(
        row,
        {
            "phase": "pre_chat",
            "codes": pre_scan.matched_codes,
            "severity": pre_scan.severity,
            "routing": pre_action,
        },
    )
    _record_audit(
        db,
        row.id,
        "safety_routing_transition",
        {
            "phase": "pre_chat",
            "severity": pre_scan.severity,
            "routing_action": pre_action,
            "codes": pre_scan.matched_codes,
            "max_after": row.safety_max_severity,
        },
    )
    if pre_action in (RoutingAction.EMERGENCY_STOP, RoutingAction.SHOW_RESOURCES_AND_END_CHAT):
        row.status = "abandoned"
        row.dropout_stage = "safety_pre_chat"
        row.arm = None
        row.safety_policy_chat_ended = True
        _touch_activity(row)
        _record_audit(
            db,
            row.id,
            "safety_pre_chat_block",
            {"severity": pre_scan.severity, "action": pre_action, "codes": pre_scan.matched_codes},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "safety_pre_chat_block",
                "action": pre_action,
                "severity": pre_scan.severity,
                "matched_codes": pre_scan.matched_codes,
                "message": (
                    "Under platform safety rules, you cannot enter the chat session right now. "
                    "This system is not continuously monitored and cannot provide emergency care. "
                    "Please open Help & resources and, if you are in immediate danger, contact local emergency services or police."
                ),
            },
        )

    arm = pick_random_arm()
    row.arm = arm
    row.status = "chat_ready"
    _reset_chat_counters(row)
    bundle = load_bundle(None)
    row.prompt_bundle_version = bundle.version_ref
    row.session_meta_json = {
        **dict(row.session_meta_json or {}),
        "participant_id": str(row.id),
        "assigned_condition": arm,
        "randomization_block": settings.randomization_mode,
        "model_id": effective_llm_model(),
        "api_type": LLM_API_TYPE_LABEL,
        "store_flag": bool(settings.llm_store_flag),
        "global_prompt_version": bundle.version_ref,
        "style_prompt_version": bundle.version_ref,
        "stage_prompt_version": bundle.version_ref,
        "strategy_library_version": load_strategies_placeholder().get("version"),
        "frontend_build": settings.frontend_build,
        "backend_build": settings.backend_build,
    }
    _touch_activity(row)
    _record_audit(
        db,
        row.id,
        "randomized",
        {
            "arm": arm,
            "prompt_version": bundle.version_ref,
            "randomization_mode": settings.randomization_mode,
            "strategy_library_version": load_strategies_placeholder().get("version"),
            "frontend_build": settings.frontend_build,
            "backend_build": settings.backend_build,
        },
    )
    db.commit()
    return RandomizeOkResponse(status=row.status, arm=arm, already_assigned=False)


@router.post("/{session_id}/chat/turn", response_model=ChatTurnResponse)
def post_chat_turn(
    body: ChatTurnBody,
    row: SessionRecord = Depends(get_current_session),
    db: OrmSession = Depends(get_db),
) -> ChatTurnResponse:
    """处理一轮用户输入：安全扫描、填槽、可选 LLM、写 chat_turns，并推进 FSM。"""
    if row.status in ("post_survey_pending", "completed"):
        raise HTTPException(status_code=400, detail="Chat has ended; no more messages can be sent.")
    if row.status == "stage1_feedback_pending":
        raise HTTPException(
            status_code=400,
            detail="Please review the Stage 1 summary and tap Continue before sending more messages.",
        )
    if row.status not in ("chat_ready", "chat_active"):
        raise HTTPException(status_code=400, detail=f"Chat is not available in status: {row.status}")
    if not row.arm:
        raise HTTPException(status_code=400, detail="Randomization not completed; cannot start chat.")

    ref = resolve_version_ref_for_session(row.prompt_bundle_version)
    bundle = load_bundle(ref)
    if row.prompt_bundle_version is None:
        row.prompt_bundle_version = bundle.version_ref

    t_recv = datetime.now(timezone.utc)
    was_chat_ready = row.status == "chat_ready"
    if was_chat_ready:
        row.status = "chat_active"
        row.chat_started_at = t_recv
        _record_audit(db, row.id, "chat_started", {"fsm_stage": row.fsm_stage})

    text_trim = body.text.strip()[:4000]
    scan = scan_user_text(text_trim)
    row.safety_max_severity = merge_session_severity(row.safety_max_severity, scan.severity)
    routing = severity_to_action(scan.severity)
    row.safety_last_routing_action = routing

    row.chat_exchange_index += 1
    exchange_index = row.chat_exchange_index

    append_safety_flag(
        row,
        {
            "phase": "in_chat",
            "exchange_index": exchange_index,
            "codes": scan.matched_codes,
            "severity": scan.severity,
            "routing": routing,
        },
    )
    _record_audit(
        db,
        row.id,
        "safety_routing_transition",
        {
            "phase": "in_chat",
            "severity": scan.severity,
            "routing_action": routing,
            "codes": scan.matched_codes,
            "max_after": row.safety_max_severity,
            "exchange_index": exchange_index,
        },
    )

    if routing == RoutingAction.EMERGENCY_STOP:
        st_em = row.fsm_stage
        row.chat_last_turn_index += 1
        turn_user = row.chat_last_turn_index
        row.chat_last_turn_index += 1
        turn_asst = row.chat_last_turn_index
        assistant_text = ASSISTANT_EMERGENCY_STOP
        t_done = datetime.now(timezone.utc)
        latency_ms = int((t_done - t_recv).total_seconds() * 1000)
        stub_meta_em: dict[str, Any] = {
            "stub": True,
            "safety_emergency": True,
            "safety_flags": scan.matched_codes,
            "safety_severity_this_turn": scan.severity,
            "safety_routing_action": RoutingAction.EMERGENCY_STOP,
            "stage_at_request": st_em,
            "exchange_index": exchange_index,
            "prompt_version": bundle.version_ref,
            "backend_controls_stage": True,
            "llm_skipped": True,
        }
        db.add(
            ChatTurn(
                session_id=row.id,
                exchange_index=exchange_index,
                turn_index=turn_user,
                role="user",
                stage=st_em,
                arm=row.arm,
                text=body.text,
                char_count=len(body.text),
                word_count=_text_word_count(body.text),
                user_text=body.text,
                assistant_text=None,
                timestamp_client_send=body.timestamp_client_send,
                latency_ms=None,
                server_received_at=t_recv,
                response_ready_at=None,
                stub_meta=stub_meta_em,
            )
        )
        db.add(
            ChatTurn(
                session_id=row.id,
                exchange_index=exchange_index,
                turn_index=turn_asst,
                role="assistant",
                stage=st_em,
                arm=row.arm,
                text=assistant_text,
                char_count=len(assistant_text),
                word_count=_text_word_count(assistant_text),
                user_text=body.text,
                assistant_text=assistant_text,
                timestamp_client_send=None,
                latency_ms=latency_ms,
                server_received_at=t_recv,
                response_ready_at=t_done,
                stub_meta=stub_meta_em,
            )
        )
        row.status = "abandoned"
        row.dropout_stage = "safety_emergency_in_chat"
        row.safety_policy_chat_ended = True
        _record_audit(
            db,
            row.id,
            "safety_emergency_stop",
            {"severity": scan.severity, "codes": scan.matched_codes, "exchange_index": exchange_index},
        )
        persist_chat_summary(db, row)
        _update_session_meta_metrics(db, row)
        _touch_activity(row)
        db.commit()
        return ChatTurnResponse(
            assistant_text=assistant_text,
            stub=True,
            stage_after=row.fsm_stage,
            exchange_index=exchange_index,
            status_after=row.status,
            chat_closed=True,
            prompt_version=bundle.version_ref,
            safety_severity_this_turn=scan.severity,
            safety_routing_action=RoutingAction.EMERGENCY_STOP,
            safety_resources_suggested=True,
        )

    st = row.fsm_stage
    slots = dict(row.slot_json or {})
    target_slot = first_missing_slot(st, slots)
    if target_slot is None:
        raise HTTPException(status_code=400, detail="Invalid slot state: no pending slot for this stage.")

    fill_key = qualified_slot_key(st, target_slot)
    slots[fill_key] = text_trim
    row.slot_json = slots

    snippet = text_trim.replace("|", " ")[:160]
    roll = (row.rolling_summary or "") + f"{fill_key}={snippet}|"
    if len(roll) > 12000:
        roll = roll[-12000:]
    row.rolling_summary = roll

    row.chat_user_turns_in_stage += 1

    if not stage_slots_complete(st, slots) and row.chat_user_turns_in_stage >= max_user_turns_for_stage(st):
        if pad_incomplete_stage_with_cap_marker(st, slots):
            row.slot_json = slots
            _record_audit(
                db,
                row.id,
                "stage_turn_cap_pad",
                {
                    "stage": st,
                    "max_turns": max_user_turns_for_stage(st),
                    "exchange_index": exchange_index,
                },
            )

    assistant_turns_before = _assistant_turns_count(db, row.id)
    budget_hard_limit = STUDY_TARGET_ASSISTANT_TURNS_MAX
    budget_force_close = assistant_turns_before >= (budget_hard_limit - 1)
    if budget_force_close:
        _force_fill_until_close(slots, st)
        row.slot_json = slots
        _record_audit(
            db,
            row.id,
            "turn_budget_exceeded",
            {
                "assistant_turns_before": assistant_turns_before,
                "assistant_turn_limit": budget_hard_limit,
                "exchange_index": exchange_index,
                "forced_from_stage": st,
            },
        )

    stage_complete = stage_slots_complete(st, slots)
    chat_closed = False
    assistant_stub = ""

    nxt: int | None = None
    if stage_complete:
        nxt = next_stage_after_completion(st)

    next_ask: str | None = None
    first_next: str | None = None
    mode = "next_slot"

    if budget_force_close:
        assistant_stub = build_assistant_slot_stub(
            row.arm,
            MAX_CHAT_STAGE,
            completing_chat=True,
            next_stage=None,
            ask_slot=None,
            bundle=bundle,
        )
        mode = "closing"
        chat_closed = True
    elif not stage_complete:
        next_ask = first_missing_slot(st, slots)
        if next_ask is None:
            raise HTTPException(status_code=500, detail="Internal slot bookkeeping mismatch.")
        assistant_stub = build_assistant_slot_stub(
            row.arm,
            st,
            completing_chat=False,
            next_stage=None,
            ask_slot=next_ask,
            bundle=bundle,
        )
        mode = "next_slot"
    elif nxt is None:
        assistant_stub = build_assistant_slot_stub(
            row.arm,
            st,
            completing_chat=True,
            next_stage=None,
            ask_slot=None,
            bundle=bundle,
        )
        mode = "closing"
        chat_closed = True
    else:
        if st == 1 and nxt == 2:
            assistant_stub = (
                "Thanks for sharing those details. On the next screen you'll see a brief recap of this section "
                "and a few numbers you entered earlier. When you're ready, tap Continue to begin the next part."
            )
            mode = "stage1_feedback_bridge"
            first_next = first_missing_slot(nxt, slots)
            if first_next is None:
                raise HTTPException(status_code=500, detail="Next stage has no slot definition.")
        else:
            first_next = first_missing_slot(nxt, slots)
            if first_next is None:
                raise HTTPException(status_code=500, detail="Next stage has no slot definition.")
            assistant_stub = build_assistant_slot_stub(
                row.arm,
                st,
                completing_chat=False,
                next_stage=nxt,
                ask_slot=first_next,
                bundle=bundle,
            )
            mode = "transition"

    policy_l2 = routing == RoutingAction.SHOW_RESOURCES_AND_END_CHAT
    llm_attempted = (
        llm_is_configured()
        and not llm_endpoint_hang_risk()
        and not policy_l2
        and mode != "stage1_feedback_bridge"
    )
    if llm_is_configured() and llm_endpoint_hang_risk():
        _record_audit(
            db,
            row.id,
            "llm_skipped_known_hang_risk",
            {"exchange_index": exchange_index, "stage": st},
        )
    llm_res = None
    assistant_text = assistant_stub
    stub_flag = True

    if policy_l2:
        assistant_text = ASSISTANT_SAFE_END_CHAT
        stub_flag = True
        llm_res = None
    elif llm_attempted:
        recent = _recent_turns_transcript(db, row.id)
        strategies_full = load_strategies_placeholder()
        next_slot_for_prompt = (
            next_ask if mode == "next_slot" else (first_next if mode == "transition" else None)
        )
        trans_stage = nxt if mode == "transition" else None
        strategies = strategies_payload_for_turn(
            strategies_full,
            stage_at_turn=st,
            next_slot_id=next_slot_for_prompt,
            slot_json=slots,
            session_id=row.id,
        )
        messages = build_turn_messages(
            bundle=bundle,
            arm=row.arm or "",
            stage_at_turn=st,
            current_substate=row.current_substate,
            slot_json=slots,
            rolling_summary=row.rolling_summary or "",
            backend_stage_complete=stage_complete,
            mode=mode,
            next_slot_id=next_slot_for_prompt,
            transition_to_stage=trans_stage,
            user_just_filled_key=fill_key,
            user_message=body.text,
            recent_transcript=recent,
            strategies=strategies,
        )
        hard_timeout_sec = 8.0
        ex = ThreadPoolExecutor(max_workers=1)
        fut = ex.submit(call_chat_turn_structured, messages)
        try:
            llm_res = fut.result(timeout=hard_timeout_sec)
            ex.shutdown(wait=False, cancel_futures=False)
        except FuturesTimeoutError:
            # 注意：不能使用 `with ThreadPoolExecutor(...)`，否则超时后 __exit__ 会等待工作线程结束，仍可能卡住请求。
            fut.cancel()
            ex.shutdown(wait=False, cancel_futures=True)
            llm_res = None
            _record_audit(
                db,
                row.id,
                "llm_hard_timeout_fallback",
                {"exchange_index": exchange_index, "stage": st, "hard_timeout_sec": hard_timeout_sec},
            )
        llm_ok = bool(getattr(llm_res, "ok", False)) if llm_res is not None else False
        llm_parsed = getattr(llm_res, "parsed", None) if llm_res is not None else None
        if llm_ok and llm_parsed:
            assistant_text = llm_parsed.assistant_text[:4000]
            stub_flag = False

    if policy_l2:
        chat_closed = True
        row.status = "post_survey_pending"
        row.chat_completed_at = datetime.now(timezone.utc)
        row.current_substate = None
        row.safety_policy_chat_ended = True
        _record_audit(db, row.id, "chat_completed_safety", {"final_stage": st, "severity": scan.severity})
    elif not stage_complete:
        row.current_substate = qualified_slot_key(st, next_ask)  # type: ignore[arg-type]
    elif chat_closed:
        row.fsm_stage = MAX_CHAT_STAGE
        row.status = "post_survey_pending"
        row.chat_completed_at = datetime.now(timezone.utc)
        row.current_substate = None
        _record_audit(db, row.id, "chat_completed", {"final_stage": st})
    elif mode == "stage1_feedback_bridge":
        row.status = "stage1_feedback_pending"
        row.fsm_stage = nxt  # type: ignore[assignment]
        row.chat_user_turns_in_stage = 0
        row.current_substate = None
        _record_audit(
            db,
            row.id,
            "stage1_feedback_pending",
            {"from_stage": st, "to_stage": nxt},
        )
    else:
        _record_audit(db, row.id, "stage_transition", {"from_stage": st, "to_stage": nxt})
        row.fsm_stage = nxt  # type: ignore[assignment]
        row.chat_user_turns_in_stage = 0
        row.current_substate = qualified_slot_key(nxt, first_next)  # type: ignore[arg-type]

    row.chat_last_turn_index += 1
    turn_user = row.chat_last_turn_index
    row.chat_last_turn_index += 1
    turn_asst = row.chat_last_turn_index

    t_done = datetime.now(timezone.utc)
    latency_ms = int((t_done - t_recv).total_seconds() * 1000)

    stub_meta: dict[str, Any] = {
        "stub": stub_flag,
        "slot_filled": fill_key,
        "stage_at_request": st,
        "stage_complete_after": stage_complete,
        "fsm_stage_after": row.fsm_stage,
        "prompt_version": bundle.version_ref,
        "backend_controls_stage": True,
        "safety_flags": scan.matched_codes,
        "safety_severity_this_turn": scan.severity,
        "safety_routing_action": routing,
    }
    if routing == RoutingAction.SHOW_RESOURCES_AND_CONTINUE:
        stub_meta["safety_resources_suggested"] = True
    if llm_attempted:
        stub_meta["llm_attempted"] = True
        if llm_res:
            row.session_meta_json = {
                **dict(row.session_meta_json or {}),
                "model_id": llm_res.model_version or effective_llm_model(),
                "api_type": llm_res.api_type,
                "store_flag": bool(settings.llm_store_flag),
                "frontend_build": settings.frontend_build,
                "backend_build": settings.backend_build,
            }
            stub_meta["llm_model"] = llm_res.model_version
            stub_meta["llm_response_id"] = llm_res.response_id
            stub_meta["llm_latency_ms"] = llm_res.latency_ms
            stub_meta["llm_input_tokens"] = llm_res.input_tokens
            stub_meta["llm_output_tokens"] = llm_res.output_tokens
            stub_meta["llm_total_tokens"] = llm_res.total_tokens
            if llm_res.ok and llm_res.parsed:
                p = llm_res.parsed
                stub_meta["model_stage_complete_advisory"] = p.stage_complete
                stub_meta["safety_level"] = p.safety_level
                stub_meta["needs_human_review"] = p.needs_human_review
                stub_meta["selected_strategy_ids"] = p.selected_strategy_ids
                stub_meta["extracted_slots"] = p.extracted_slots
                stub_meta["dialogue_acts"] = p.dialogue_acts
                stub_meta["next_action"] = p.next_action
                stub_meta["model_reported_stage"] = p.model_reported_stage
                stub_meta["llm_risk_block"] = p.risk.model_dump()
                stub_meta["llm_api_type"] = llm_res.api_type
                stub_meta["llm_retry_count"] = llm_res.retry_count
                stub_meta["llm_refusal_flag"] = llm_res.refusal_flag
                if llm_res.finish_reason:
                    stub_meta["llm_finish_reason"] = llm_res.finish_reason
                if llm_res.fallback_reason:
                    stub_meta["llm_fallback_reason"] = llm_res.fallback_reason
            elif llm_res.error:
                stub_meta["llm_error"] = llm_res.error
    else:
        stub_meta["llm_skipped"] = True
        stub_meta["style_fidelity"] = _heuristic_style_fidelity(assistant_text)
    if "style_fidelity" not in stub_meta:
        stub_meta["style_fidelity"] = _heuristic_style_fidelity(assistant_text)
    _record_audit(
        db,
        row.id,
        "style_fidelity_tagged",
        {
            "exchange_index": exchange_index,
            "stage": st,
            "tags": stub_meta["style_fidelity"],
        },
    )
    selected_strategy_ids_for_state: list[str] = []
    if llm_res and llm_res.ok and llm_res.parsed:
        selected_strategy_ids_for_state = list(llm_res.parsed.selected_strategy_ids or [])

    if llm_attempted:
        db.add(
            LlmCall(
                session_id=row.id,
                exchange_index=exchange_index,
                prompt_version=bundle.version_ref,
                model_version=(llm_res.model_version if llm_res else effective_llm_model()) or "",
                api_type=(llm_res.api_type if llm_res else LLM_API_TYPE_LABEL),
                response_id=llm_res.response_id if llm_res and llm_res.ok else None,
                previous_response_id=llm_res.previous_response_id if llm_res and llm_res.ok else None,
                latency_ms=llm_res.latency_ms if llm_res else 0,
                prompt_tokens=llm_res.input_tokens if llm_res else None,
                completion_tokens=llm_res.output_tokens if llm_res else None,
                total_tokens=llm_res.total_tokens if llm_res else None,
                success=bool(llm_res and llm_res.ok),
                fallback_used=stub_flag,
                fallback_reason=(llm_res.fallback_reason if llm_res else None),
                retry_count=(llm_res.retry_count if llm_res else 0),
                finish_reason=(llm_res.finish_reason if llm_res else None),
                refusal_flag=(llm_res.refusal_flag if llm_res else False),
                error_message=None
                if (llm_res and llm_res.ok)
                else (llm_res.error if llm_res else "llm_no_response"),
                normalized_output=(
                    llm_res.parsed.model_dump() if llm_res and llm_res.ok and llm_res.parsed else None
                ),
                raw_content=llm_res.raw_content if llm_res else None,
            )
        )

    db.add(
        ChatTurn(
            session_id=row.id,
            exchange_index=exchange_index,
            turn_index=turn_user,
            role="user",
            stage=st,
            arm=row.arm,
            text=body.text,
            char_count=len(body.text),
            word_count=_text_word_count(body.text),
            user_text=body.text,
            assistant_text=None,
            timestamp_client_send=body.timestamp_client_send,
            latency_ms=None,
            server_received_at=t_recv,
            response_ready_at=None,
            stub_meta=stub_meta,
        )
    )
    db.add(
        ChatTurn(
            session_id=row.id,
            exchange_index=exchange_index,
            turn_index=turn_asst,
            role="assistant",
            stage=st,
            arm=row.arm,
            text=assistant_text,
            char_count=len(assistant_text),
            word_count=_text_word_count(assistant_text),
            user_text=body.text,
            assistant_text=assistant_text,
            timestamp_client_send=None,
            latency_ms=latency_ms,
            server_received_at=t_recv,
            response_ready_at=t_done,
            stub_meta=stub_meta,
        )
    )

    _append_stage_state_event(
        db,
        row,
        turn_index=turn_asst,
        current_stage=row.fsm_stage,
        slots=slots,
        stage_complete=stage_complete,
        reason_for_transition=(
            "turn_budget_force_close"
            if budget_force_close
            else ("stage_complete" if stage_complete else "slot_update")
        ),
        selected_strategy_ids=selected_strategy_ids_for_state,
    )

    if row.status == "post_survey_pending":
        persist_chat_summary(db, row)
    _update_session_meta_metrics(db, row)
    _touch_activity(row)
    db.commit()

    res_suggest = routing == RoutingAction.SHOW_RESOURCES_AND_CONTINUE
    return ChatTurnResponse(
        assistant_text=assistant_text,
        stub=stub_flag,
        stage_after=row.fsm_stage,
        exchange_index=exchange_index,
        status_after=row.status,
        chat_closed=chat_closed,
        stage1_feedback_required=(mode == "stage1_feedback_bridge"),
        prompt_version=bundle.version_ref,
        safety_severity_this_turn=scan.severity,
        safety_routing_action=routing,
        safety_resources_suggested=res_suggest,
    )


@router.post("/{session_id}/chat/stage1-feedback/continue", response_model=Stage1FeedbackContinueResponse)
def post_stage1_feedback_continue(
    row: SessionRecord = Depends(get_current_session),
    db: OrmSession = Depends(get_db),
) -> Stage1FeedbackContinueResponse:
    """参与者看完 Stage1 反馈卡后恢复聊天，并下发 Stage2 首问（写入一对 synthetic user + assistant turns）。"""
    if row.status != "stage1_feedback_pending":
        raise HTTPException(status_code=400, detail="Stage 1 feedback is not pending for this session.")
    if not row.arm:
        raise HTTPException(status_code=400, detail="Randomization not completed; cannot continue chat.")

    ref = resolve_version_ref_for_session(row.prompt_bundle_version)
    bundle = load_bundle(ref)
    if row.prompt_bundle_version is None:
        row.prompt_bundle_version = bundle.version_ref

    slots = dict(row.slot_json or {})
    next_slot = first_missing_slot(2, slots)
    if next_slot is None:
        raise HTTPException(status_code=500, detail="No Stage 2 slot to ask after Stage 1 feedback.")

    assistant_text = build_assistant_slot_stub(
        row.arm,
        1,
        completing_chat=False,
        next_stage=2,
        ask_slot=next_slot,
        bundle=bundle,
    )
    row.status = "chat_active"
    row.current_substate = qualified_slot_key(2, next_slot)

    t_recv = datetime.now(timezone.utc)
    row.chat_exchange_index += 1
    ex = row.chat_exchange_index
    row.chat_last_turn_index += 1
    turn_user = row.chat_last_turn_index
    row.chat_last_turn_index += 1
    turn_asst = row.chat_last_turn_index
    synthetic = "[stage1_feedback_continue]"
    stub_meta: dict[str, Any] = {
        "stub": True,
        "stage1_feedback_continue": True,
        "prompt_version": bundle.version_ref,
    }
    db.add(
        ChatTurn(
            session_id=row.id,
            exchange_index=ex,
            turn_index=turn_user,
            role="user",
            stage=2,
            arm=row.arm,
            text=synthetic,
            char_count=len(synthetic),
            word_count=_text_word_count(synthetic),
            user_text=synthetic,
            assistant_text=None,
            timestamp_client_send=None,
            latency_ms=None,
            server_received_at=t_recv,
            response_ready_at=None,
            stub_meta=stub_meta,
        )
    )
    t_done = datetime.now(timezone.utc)
    latency_ms = int((t_done - t_recv).total_seconds() * 1000)
    db.add(
        ChatTurn(
            session_id=row.id,
            exchange_index=ex,
            turn_index=turn_asst,
            role="assistant",
            stage=2,
            arm=row.arm,
            text=assistant_text,
            char_count=len(assistant_text),
            word_count=_text_word_count(assistant_text),
            user_text=synthetic,
            assistant_text=assistant_text,
            timestamp_client_send=None,
            latency_ms=latency_ms,
            server_received_at=t_recv,
            response_ready_at=t_done,
            stub_meta=stub_meta,
        )
    )
    _append_stage_state_event(
        db,
        row,
        turn_index=turn_asst,
        current_stage=2,
        slots=slots,
        stage_complete=False,
        reason_for_transition="stage1_feedback_continue",
        selected_strategy_ids=[],
    )
    _record_audit(db, row.id, "stage1_feedback_continued", {"exchange_index": ex})
    _touch_activity(row)
    db.commit()
    return Stage1FeedbackContinueResponse(
        ok=True,
        assistant_text=assistant_text,
        stub=True,
        status_after=row.status,
        exchange_index=ex,
        prompt_version=bundle.version_ref,
    )


@router.post("/{session_id}/surveys/post", response_model=PostSurveyOkResponse)
def post_post_survey(
    body: PostSurveySubmit,
    row: SessionRecord = Depends(get_current_session),
    db: OrmSession = Depends(get_db),
) -> PostSurveyOkResponse:
    """提交后测问卷，主流程标记为 completed。"""
    if row.status != "post_survey_pending":
        raise HTTPException(status_code=400, detail=f"Post-survey cannot be submitted in status: {row.status}")
    if _survey_exists(db, row.id, "post"):
        raise HTTPException(status_code=409, detail="Post-survey was already submitted.")

    payload = body.model_dump()
    payload["wai_tech_sf_total_12_84"] = sum(int(payload[f"wai_tech_sf_item_{i:02d}"]) for i in range(1, 13))
    db.add(
        SurveyResponse(
            session_id=row.id,
            instrument="post",
            schema_version=SURVEY_SCHEMA_POST,
            answers=payload,
        )
    )
    row.status = "completed"
    _update_session_meta_metrics(db, row)
    _touch_activity(row)
    _record_audit(db, row.id, "post_survey_submitted", {"schema_version": SURVEY_SCHEMA_POST})
    db.commit()
    return PostSurveyOkResponse(status=row.status)


@router.post("/{session_id}/followup/opt-in", response_model=FollowUpOptInOkResponse)
def followup_opt_in(
    body: FollowUpOptInBody,
    row: SessionRecord = Depends(get_current_session),
    db: OrmSession = Depends(get_db),
) -> FollowUpOptInOkResponse:
    """主流程完成后登记随访联系方式并生成公开 token（已存在则返回原 token）。"""
    if row.status != "completed":
        raise HTTPException(
            status_code=400,
            detail="Follow-up opt-in is only available after the main flow is completed; finish the post-survey first.",
        )

    q = select(SessionFollowup).where(SessionFollowup.session_id == row.id)
    existing = db.scalars(q).one_or_none()
    if existing:
        return FollowUpOptInOkResponse(
            followup_token=existing.followup_token,
            followup_public_path=f"/follow-up/{existing.followup_token}",
        )

    token = secrets.token_urlsafe(32)
    fu = SessionFollowup(
        session_id=row.id,
        followup_token=token,
        contact_json={
            "email": (body.contact_email or "").strip() or None,
            "phone": (body.contact_phone or "").strip() or None,
        },
        opt_in_at=datetime.now(timezone.utc),
    )
    db.add(fu)
    _record_audit(
        db,
        row.id,
        "followup_opt_in",
        {
            "has_email": bool((body.contact_email or "").strip()),
            "has_phone": bool((body.contact_phone or "").strip()),
        },
    )
    _touch_activity(row)
    db.commit()
    return FollowUpOptInOkResponse(
        followup_token=token,
        followup_public_path=f"/follow-up/{token}",
    )
