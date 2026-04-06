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

    base = {
        "typical_drinks_last_week": 12,
        "readiness_to_change_1_10": 6,
    }
    assert client.post(f"/api/v1/sessions/{sid}/surveys/baseline", json=base, headers=h).status_code == 200

    rz = client.post(f"/api/v1/sessions/{sid}/randomize", headers=h)
    assert rz.status_code == 200, rz.text
    arm = rz.json()["arm"]
    return sid, token, arm


def test_stage_progression_and_chat_close(client: TestClient) -> None:
    sid, token, _arm = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)

    # 每阶段按 required_slots 填满后才推进；共 9 条用户消息
    expected_stage_after = [0, 1, 1, 2, 2, 3, 3, 4, 4]
    chat_closed_flags: list[bool] = []
    for i in range(9):
        r = client.post(f"/api/v1/sessions/{sid}/chat/turn", json={"text": f"m{i}"}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["stub"] is True
        assert body["stage_after"] == expected_stage_after[i]
        assert body.get("prompt_version") == "safechat-aud@0.2.1"
        chat_closed_flags.append(body["chat_closed"])

    assert chat_closed_flags[-1] is True
    assert all(not x for x in chat_closed_flags[:-1])

    r10 = client.post(f"/api/v1/sessions/{sid}/chat/turn", json={"text": "too late"}, headers=h)
    assert r10.status_code == 400

    st_end = client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()
    assert st_end.get("chat_summary") is not None
    assert st_end["chat_summary"].get("schema_version") == "1"


def test_chat_summary_persistence_has_export_keys(client: TestClient) -> None:
    """验收：摘要卡 JSON 含分析用键（与 docs/data-dictionary-export-spec.md 一致）。"""
    sid, token, _ = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)
    for i in range(9):
        assert (
            client.post(f"/api/v1/sessions/{sid}/chat/turn", json={"text": f"slot{i}"}, headers=h).status_code
            == 200
        )
    summary = client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()["chat_summary"]
    assert summary is not None
    for key in (
        "schema_version",
        "top_reason_to_cut_down",
        "top_trigger_high_risk_situation",
        "trigger_context",
        "support_focus",
        "micro_plan_if_then",
        "change_readiness_baseline_1_10",
        "optional_takeaway",
        "confidence_summary",
    ):
        assert key in summary


def test_acceptance_e2e_linear_to_completed(client: TestClient) -> None:
    """验收：单会话线性完成至 completed（无 LLM，等同主力 API 路径）。"""
    sid, token, _ = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)
    for i in range(9):
        r = client.post(f"/api/v1/sessions/{sid}/chat/turn", json={"text": f"turn{i}"}, headers=h)
        assert r.status_code == 200, r.text
    st = client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()
    assert st["status"] == "post_survey_pending"
    assert st.get("chat_summary") is not None

    body = _sample_post_survey_json()
    body["open_most_helpful"] = "闭环。"
    body["open_unnatural_or_uncomfortable"] = "无。"
    assert client.post(f"/api/v1/sessions/{sid}/surveys/post", json=body, headers=h).status_code == 200
    assert client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()["status"] == "completed"


def _sample_post_survey_json() -> dict:
    return {
        "therapeutic_alliance_1_5": 4,
        "trust_1_5": 4,
        "helpfulness_1_5": 4,
        "disclosure_comfort_1_5": 4,
        "change_intention_1_5": 4,
        "manipulation_felt_warm_1_5": 3,
        "manipulation_felt_professional_1_5": 4,
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

    for _ in range(9):
        assert (
            client.post(f"/api/v1/sessions/{sid}/chat/turn", json={"text": "x"}, headers=h).status_code
            == 200
        )

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
    for k in range(3):
        client.post(f"/api/v1/sessions/{sid}/chat/turn", json={"text": str(k)}, headers=h)
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

    base = {
        "typical_drinks_last_week": 12,
        "readiness_to_change_1_10": 6,
    }
    assert client.post(f"/api/v1/sessions/{sid}/surveys/baseline", json=base, headers=h).status_code == 200
    return sid, token


def test_simulation_forces_arm_on_randomize(client: TestClient) -> None:
    from app.config import settings

    for arm in ("empathic", "neutral"):
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
        assert rz.json()["arm"] == arm


def test_followup_public_token_open_and_submit(client: TestClient) -> None:
    """验收：随访 opt-in → 公开 GET/POST token → 重复提交 409。"""
    sid, token, _ = _bootstrap_to_chat_ready(client)
    h = _auth_headers(token)
    for _ in range(9):
        assert (
            client.post(f"/api/v1/sessions/{sid}/chat/turn", json={"text": "x"}, headers=h).status_code == 200
        )
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
