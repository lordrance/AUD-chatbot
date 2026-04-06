"""PostgreSQL 集成：三条安全路由（不重写安全逻辑，仅行为验收）。"""

import pytest
from fastapi.testclient import TestClient

import app.config as app_config
from app.constants import CONSENT_DOCUMENT_VERSION
from app.services.prompt_registry import clear_bundle_cache

from tests.integration_env import INTEGRATION_SKIP_REASON, is_integration_db_configured

pytestmark = pytest.mark.skipif(
    not is_integration_db_configured(),
    reason=INTEGRATION_SKIP_REASON,
)


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config.settings, "openai_api_key", None)
    monkeypatch.setattr(app_config.settings, "gemini_api_key", None)


@pytest.fixture(autouse=True)
def _prompt_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config.settings, "prompt_bundle_version", "0.2.1")
    clear_bundle_cache()
    yield
    clear_bundle_cache()


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _to_pending_randomize_with_concern(client: TestClient, concern: str | None) -> tuple[str, str]:
    r = client.post("/api/v1/sessions")
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    token = r.json()["session_token"]
    h = _h(token)

    consent = {"consent_accepted": True, "consent_document_version": CONSENT_DOCUMENT_VERSION}
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
        "importance_to_reduce_0_10": 7,
        "prior_chatbot_or_ai_use": "never",
        "in_treatment_for_aud_or_mental_health": False,
        "education_level": "college_grad",
        "employment_status": "employed",
    }
    if concern is not None:
        base["primary_concern_short"] = concern
    assert client.post(f"/api/v1/sessions/{sid}/surveys/baseline", json=base, headers=h).status_code == 200
    return sid, token


def _to_chat_ready(client: TestClient) -> tuple[str, str]:
    sid, token = _to_pending_randomize_with_concern(client, None)
    h = _h(token)
    rz = client.post(f"/api/v1/sessions/{sid}/randomize", headers=h)
    assert rz.status_code == 200, rz.text
    return sid, token


def test_pre_chat_severity2_randomize_403(client: TestClient) -> None:
    sid, token = _to_pending_randomize_with_concern(
        client,
        "我最近想伤害自己，觉得很痛苦",
    )
    h = _h(token)
    rz = client.post(f"/api/v1/sessions/{sid}/randomize", headers=h)
    assert rz.status_code == 403
    detail = rz.json()["detail"]
    assert detail.get("code") == "safety_pre_chat_block"
    st = client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()
    assert st["status"] == "abandoned"


def test_in_chat_severity2_ends_to_post_survey_pending(client: TestClient) -> None:
    sid, token = _to_chat_ready(client)
    h = _h(token)
    r = client.post(
        f"/api/v1/sessions/{sid}/chat/turn",
        json={"text": "我想伤害自己，不知道怎么办"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status_after"] == "post_survey_pending"
    assert body["chat_closed"] is True

    st = client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()
    assert st["post_survey_unlocked"] is True
    assert st.get("chat_summary") is not None
    assert st["chat_summary"].get("schema_version") == "2"


def test_in_chat_severity3_abandoned(client: TestClient) -> None:
    sid, token = _to_chat_ready(client)
    h = _h(token)
    r = client.post(
        f"/api/v1/sessions/{sid}/chat/turn",
        json={"text": "我不想活了今晚就自杀"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status_after"] == "abandoned"

    st = client.get(f"/api/v1/sessions/{sid}/state", headers=h).json()
    assert st["status"] == "abandoned"
