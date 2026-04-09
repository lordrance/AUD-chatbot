import uuid

import pytest
from fastapi.testclient import TestClient

import app.config as app_config
from app.constants import CONSENT_DOCUMENT_VERSION, SURVEY_SCHEMA_FOLLOWUP_7D
from app.services.prompt_registry import clear_bundle_cache

from tests.integration_env import INTEGRATION_SKIP_REASON, is_integration_db_configured

pytestmark = pytest.mark.skipif(
    not is_integration_db_configured(),
    reason=INTEGRATION_SKIP_REASON,
)


@pytest.fixture(autouse=True)
def _disable_real_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """集成测试不调用真实 LLM（OpenAI/Gemini），避免消耗密钥与不稳定。"""
    monkeypatch.setattr(app_config.settings, "openai_api_key", None)
    monkeypatch.setattr(app_config.settings, "gemini_api_key", None)


@pytest.fixture(autouse=True)
def _prompt_bundle_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config.settings, "prompt_bundle_version", "0.2.1")
    clear_bundle_cache()
    yield
    clear_bundle_cache()


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _post_chat_turn_ack_stage1(client: TestClient, sid: str, token: str, text: str) -> dict:
    """发送一轮聊天；若触发 Stage1 反馈闸，则自动 POST continue。"""
    h = _auth_headers(token)
    r = client.post(f"/api/v1/sessions/{sid}/chat/turn", json={"text": text}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    if body.get("stage1_feedback_required"):
        c = client.post(f"/api/v1/sessions/{sid}/chat/stage1-feedback/continue", headers=h)
        assert c.status_code == 200, c.text
    return body


def _baseline_payload() -> dict:
    """与 BaselineSubmit schema v2 对齐的最小合法体。"""
    return {
        "typical_drinks_last_week": 12,
        "readiness_to_change_1_10": 6,
        "importance_to_reduce_0_10": 7,
        "prior_chatbot_or_ai_use": "never",
        "in_treatment_for_aud_or_mental_health": False,
        "education_level": "college_grad",
        "employment_status": "employed",
    }


# 对齐 answer2.pdf 槽位：23 轮输入（Stage0=2, Stage1=5, Stage2=6, Stage3=5, Stage4=5）。
CHAT_TURNS_23: list[str] = [
    "Alex",
    "Yes, ready to start.",
    "About three times last week, a few drinks each time.",
    "Last Friday I drank more than I wanted.",
    "I want better sleep and mornings.",
    "8",
    "7",
    "After-work social pressure.",
    "Restaurant or bar near work.",
    "Thursday and Friday evenings.",
    "Coworkers and clients.",
    "Anxious and rushed.",
    "First round ordered for the table.",
    "delay_first_drink",
    "If it's a work dinner, I'll order water for the first round.",
    "I feel too tired to resist.",
    "I'll set a one-drink limit text to myself.",
    "8",
    "Better sleep and fewer rough mornings.",
    "After-work social drinking.",
    "If work dinner, water first then decide.",
    "8",
    "none",
]


def _run_chat_until_closed(client: TestClient, sid: str, token: str, turns: list[str]) -> list[dict]:
    """按 turns 逐轮发送，遇 chat_closed 即停，返回每轮响应。"""
    out: list[dict] = []
    for text in turns:
        body = _post_chat_turn_ack_stage1(client, sid, token, text)
        out.append(body)
        if body.get("chat_closed"):
            break
    return out


def _bootstrap_to_chat_ready(client: TestClient) -> tuple[str, str, str]:
    """返回 (session_id, token, arm)。"""
    r = client.post("/api/v1/sessions")
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    token = r.json()["session_token"]
    h = _auth_headers(token)

    consent = {
        "consent_accepted": True,
        "consent_document_version": CONSENT_DOCUMENT_VERSION,
    }
    assert client.post(f"/api/v1/sessions/{sid}/consent", json=consent, headers=h).status_code == 200

    elig = {
        "age_years": 30,
        "sex_at_birth": "male",
        "audit_c_frequency": 3,
        "audit_c_typical_quantity": 2,
        "audit_c_binge": 2,
        "wants_to_reduce_drinking": True,
    }
    assert client.post(f"/api/v1/sessions/{sid}/eligibility", json=elig, headers=h).status_code == 200

    assert (
        client.post(f"/api/v1/sessions/{sid}/surveys/baseline", json=_baseline_payload(), headers=h).status_code
        == 200
    )

    rz = client.post(f"/api/v1/sessions/{sid}/randomize", headers=h)
    assert rz.status_code == 200, rz.text
    arm = rz.json()["arm"]
    return sid, token, arm


def test_stage_progression_and_chat_close(client: TestClient) -> None:
    sid, token, _arm = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)

    chat_closed_flags: list[bool] = []
    for i, text in enumerate(CHAT_TURNS_23):
        body = _post_chat_turn_ack_stage1(client, sid, token, text)
        assert body["stub"] is True
        assert body.get("prompt_version") == "safechat-aud@0.2.1"
        chat_closed_flags.append(body["chat_closed"])
        if body["chat_closed"]:
            break

    assert chat_closed_flags[-1] is True
    assert all(not x for x in chat_closed_flags[:-1])

    r_extra = client.post(f"/api/v1/sessions/{sid}/chat/turn", json={"text": "too late"}, headers=h)
    assert r_extra.status_code == 400

    st_end = client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()
    assert st_end.get("chat_summary") is not None
    assert st_end["chat_summary"].get("schema_version") == "4"


def test_chat_summary_persistence_has_export_keys(client: TestClient) -> None:
    """摘要 JSON 含 v2 与兼容键。"""
    sid, token, _ = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)
    _run_chat_until_closed(client, sid, token, CHAT_TURNS_23)
    summary = client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()["chat_summary"]
    assert summary is not None
    assert summary.get("schema_version") == "4"
    for key in (
        "top_reason",
        "top_trigger",
        "chosen_plan",
        "micro_plan_if_then",
        "trigger_context",
        "selected_strategy",
        "optional_takeaway",
        "confidence_summary",
        "top_reason_to_cut_down",
        "top_trigger_high_risk_situation",
        "support_focus",
        "importance_to_reduce_baseline_0_10",
        "pdf_summary_plan",
        "pdf_if_then_plan",
    ):
        assert key in summary


def test_stage1_feedback_pending_blocks_chat_until_continue(client: TestClient) -> None:
    """完成 Stage1 后进入 stage1_feedback_pending；未 continue 前不得再 POST chat/turn。"""
    sid, token, _ = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)
    saw_feedback = False
    for text in CHAT_TURNS_23:
        r = client.post(f"/api/v1/sessions/{sid}/chat/turn", json={"text": text}, headers=h)
        assert r.status_code == 200, r.text
        if r.json().get("stage1_feedback_required"):
            saw_feedback = True
            break
    assert saw_feedback
    assert client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()["status"] == "stage1_feedback_pending"
    bad = client.post(f"/api/v1/sessions/{sid}/chat/turn", json={"text": "nope"}, headers=h)
    assert bad.status_code == 400
    assert (
        client.post(f"/api/v1/sessions/{sid}/chat/stage1-feedback/continue", headers=h).status_code == 200
    )


def test_stage3_low_confidence_forces_shrink_slots(client: TestClient) -> None:
    """末段信心 <7 时必须多 2 轮才结束聊天。"""
    sid, token, _ = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)
    # 将 Stage3 末信心改为 5，触发缩小分支；
    # 追加的 2 轮必须紧跟 Stage3（而不是放到 Stage4 之后）。
    turns = (
        list(CHAT_TURNS_23[:17])
        + ["5"]
        + [
            "If stressed, I will wait five minutes before any drink.",
            "7",
        ]
        + list(CHAT_TURNS_23[18:])
    )
    n = len(turns)
    assert n == 25
    _run_chat_until_closed(client, sid, token, turns)
    st = client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()
    assert st["status"] == "post_survey_pending"
    slots = st.get("slot_json") or {}
    assert "3:if_then_plan_revised" in slots
    assert "3:final_confidence_0_10_after_shrink" in slots


def test_acceptance_e2e_linear_to_completed(client: TestClient) -> None:
    """验收：单会话线性完成至 completed（无 LLM，等同主力 API 路径）。"""
    sid, token, _ = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)
    _run_chat_until_closed(client, sid, token, CHAT_TURNS_23)
    st = client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()
    assert st["status"] == "post_survey_pending"
    assert st.get("chat_summary") is not None

    body = _sample_post_survey_json()
    body["open_most_helpful"] = "闭环。"
    body["open_unnatural_or_uncomfortable"] = "无。"
    assert client.post(f"/api/v1/sessions/{sid}/surveys/post", json=body, headers=h).status_code == 200
    assert client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()["status"] == "completed"


def _sample_post_survey_json() -> dict:
    wai = {f"wai_tech_sf_item_{i:02d}": 5 for i in range(1, 13)}
    return {
        **wai,
        "trust_1_5": 4,
        "helpfulness_1_5": 4,
        "disclosure_comfort_1_5": 4,
        "change_intention_1_5": 4,
        "manipulation_felt_warm_1_5": 3,
        "manipulation_felt_professional_1_5": 4,
        "manipulation_felt_practical_actionable_1_5": 3,
        "manipulation_understood_feelings_1_5": 3,
        "manipulation_felt_repetitive_1_5": 2,
        "manipulation_felt_personal_tailored_1_5": 4,
        "open_most_helpful": "—",
        "open_unnatural_or_uncomfortable": "—",
    }


def test_post_survey_only_after_chat_completed(client: TestClient) -> None:
    sid, token, _ = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)

    bad = client.post(
        f"/api/v1/sessions/{sid}/surveys/post",
        json=_sample_post_survey_json(),
        headers=h,
    )
    assert bad.status_code == 400

    _run_chat_until_closed(client, sid, token, CHAT_TURNS_23)

    st = client.get(f"/api/v1/sessions/{sid}/state", headers=h)
    assert st.status_code == 200
    assert st.json()["post_survey_unlocked"] is True

    post_body = _sample_post_survey_json()
    post_body["open_most_helpful"] = "结构清晰。"
    post_body["open_unnatural_or_uncomfortable"] = "无。"
    ok = client.post(f"/api/v1/sessions/{sid}/surveys/post", json=post_body, headers=h)
    assert ok.status_code == 200
    assert ok.json()["status"] == "completed"


def test_randomize_arm_idempotent(client: TestClient) -> None:
    sid, token, arm = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)
    r2 = client.post(f"/api/v1/sessions/{sid}/randomize", headers=h)
    assert r2.status_code == 200
    assert r2.json()["already_assigned"] is True
    assert r2.json()["arm"] == arm


def test_arm_fixed_during_chat(client: TestClient) -> None:
    sid, token, arm = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)
    for text in CHAT_TURNS_23[:3]:
        _post_chat_turn_ack_stage1(client, sid, token, text)
        st = client.get(f"/api/v1/sessions/{sid}/state", headers=h)
        assert st.json()["arm"] == arm


def _bootstrap_to_pending_randomization(client: TestClient) -> tuple[str, str]:
    r = client.post("/api/v1/sessions")
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    token = r.json()["session_token"]
    h = _auth_headers(token)

    consent = {
        "consent_accepted": True,
        "consent_document_version": CONSENT_DOCUMENT_VERSION,
    }
    assert client.post(f"/api/v1/sessions/{sid}/consent", json=consent, headers=h).status_code == 200

    elig = {
        "age_years": 30,
        "sex_at_birth": "male",
        "audit_c_frequency": 3,
        "audit_c_typical_quantity": 2,
        "audit_c_binge": 2,
        "wants_to_reduce_drinking": True,
    }
    assert client.post(f"/api/v1/sessions/{sid}/eligibility", json=elig, headers=h).status_code == 200

    assert (
        client.post(f"/api/v1/sessions/{sid}/surveys/baseline", json=_baseline_payload(), headers=h).status_code
        == 200
    )
    return sid, token


def test_simulation_forces_arm_on_randomize(client: TestClient) -> None:
    from app.config import settings
    from app.services.arm_styles import canonicalize_arm

    for arm in (
        "warm_empathic",
        "neutral_professional",
        "supportive_practical",
        "empathic",
        "neutral",
    ):
        sid, token = _bootstrap_to_pending_randomization(client)
        h = _auth_headers(token)
        settings.simulation_mode = True
        settings.simulation_force_arm = arm
        try:
            rz = client.post(f"/api/v1/sessions/{sid}/randomize", headers=h)
        finally:
            settings.simulation_mode = False
            settings.simulation_force_arm = None
        assert rz.status_code == 200, rz.text
        assert rz.json()["arm"] == canonicalize_arm(arm)


def test_followup_public_token_open_and_submit(client: TestClient) -> None:
    """验收：随访 opt-in → 公开 GET/POST token → 重复提交 409。"""
    sid, token, _ = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)
    _run_chat_until_closed(client, sid, token, CHAT_TURNS_23)
    post_body = _sample_post_survey_json()
    post_body["open_most_helpful"] = "ok"
    post_body["open_unnatural_or_uncomfortable"] = "ok"
    assert client.post(f"/api/v1/sessions/{sid}/surveys/post", json=post_body, headers=h).status_code == 200

    opt = client.post(
        f"/api/v1/sessions/{sid}/followup/opt-in",
        json={"opted_in": True, "contact_email": "participant@example.invalid"},
        headers=h,
    )
    assert opt.status_code == 200, opt.text
    data = opt.json()
    fu_token = data["followup_token"]
    assert data["followup_public_path"] == f"/follow-up/{fu_token}"

    g1 = client.get(f"/api/v1/follow-up/{fu_token}")
    assert g1.status_code == 200, g1.text
    assert g1.json()["schema_version"] == SURVEY_SCHEMA_FOLLOWUP_7D
    assert g1.json()["can_submit"] is True
    assert g1.json()["already_submitted"] is False

    submit_body = {
        "drinking_days_last_7": 3,
        "heavy_drinking_days_last_7": 1,
        "used_plan": "somewhat",
        "intention_confidence_reduce_1_10": 6,
        "willing_to_use_again_1_5": 4,
    }
    p1 = client.post(f"/api/v1/follow-up/{fu_token}", json=submit_body)
    assert p1.status_code == 200, p1.text

    g2 = client.get(f"/api/v1/follow-up/{fu_token}")
    assert g2.json()["already_submitted"] is True
    assert g2.json()["can_submit"] is False

    p2 = client.post(f"/api/v1/follow-up/{fu_token}", json=submit_body)
    assert p2.status_code == 409


def test_state_exposes_chat_flags(client: TestClient) -> None:
    sid, token, _ = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)
    s0 = client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()
    assert s0["chat_open"] is True
    assert s0["chat_stage"] == 0
    assert s0["post_survey_unlocked"] is False

    uuid.UUID(str(sid))  # valid id shape
