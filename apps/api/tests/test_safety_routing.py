"""规则型安全扫描单测（无需数据库）。"""

from fastapi.testclient import TestClient

from app.constants import CONSENT_DOCUMENT_VERSION
from app.services.safety_routing import RoutingAction, scan_user_text, severity_to_action


def test_severity_to_action_table() -> None:
    assert severity_to_action(0) == RoutingAction.CONTINUE
    assert severity_to_action(1) == RoutingAction.SHOW_RESOURCES_AND_CONTINUE
    assert severity_to_action(2) == RoutingAction.SHOW_RESOURCES_AND_END_CHAT
    assert severity_to_action(3) == RoutingAction.EMERGENCY_STOP


def test_scan_empty_is_zero() -> None:
    r = scan_user_text("")
    assert r.severity == 0
    assert r.matched_codes == []


def test_scan_distress_zh_level1() -> None:
    r = scan_user_text("我最近真的崩溃到撑不住")
    assert r.severity >= 1


def test_scan_self_harm_level2_plus() -> None:
    r = scan_user_text("我有时会想伤害自己，觉得很绝望")
    assert r.severity >= 2


def test_scan_immediate_si_level3() -> None:
    r = scan_user_text("我不想活了，今晚就自杀")
    assert r.severity >= 3


def test_consent_markdown_loads() -> None:
    from app.services.consent_document import load_consent_markdown

    text = load_consent_markdown()
    assert "consent" in text.lower() or "informed" in text.lower()
    assert "2026-04-04-v1" in text


def test_consent_document_public_endpoint() -> None:
    from app.main import app

    r = TestClient(app).get("/api/v1/consent-document")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["consent_document_version"] == CONSENT_DOCUMENT_VERSION
    assert data.get("format") == "markdown"
    assert len(data.get("body", "")) > 50
