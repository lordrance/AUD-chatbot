import json
from unittest.mock import MagicMock, patch

import pytest

import app.config as app_config
from app.services.llm_client import call_chat_turn_structured


def _valid_payload() -> str:
    return json.dumps(
        {
            "assistant_text": "Thanks—please continue with a brief answer.",
            "extracted_slot_entries": [{"key": "note", "value": "x"}],
            "stage_complete": True,
            "selected_strategy_ids": ["s1"],
            "safety_level": 0,
            "needs_human_review": False,
            "dialogue_acts": ["open_question"],
            "next_action": "ask_followup",
            "model_reported_stage": "stage1",
            "risk": {"level": 0, "reason": None},
        },
        ensure_ascii=False,
    )


def test_llm_success_parses_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config.settings, "llm_provider", "openai")
    monkeypatch.setattr(app_config.settings, "openai_api_key", "sk-test-key")
    monkeypatch.setattr(app_config.settings, "openai_base_url", None)

    mock_client = MagicMock()
    mock_client.responses.create.return_value = MagicMock(
        output_text=_valid_payload(),
        model="gpt-4o-mini",
        id="resp-test-1",
        usage=MagicMock(input_tokens=10, output_tokens=20, total_tokens=30),
    )

    with patch("app.services.llm_client._client", return_value=mock_client):
        r = call_chat_turn_structured([{"role": "user", "content": "hi"}])

    kw = mock_client.responses.create.call_args.kwargs
    assert kw["response_format"]["type"] == "json_schema"
    assert r.ok
    assert r.parsed is not None
    assert "brief" in r.parsed.assistant_text.lower()
    assert r.parsed.extracted_slots.get("note") == "x"
    assert r.response_id == "resp-test-1"
    assert r.input_tokens == 10
    assert r.output_tokens == 20
    assert r.total_tokens == 30


def test_llm_invalid_json_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config.settings, "llm_provider", "openai")
    monkeypatch.setattr(app_config.settings, "openai_api_key", "sk-test-key")

    mock_client = MagicMock()
    mock_client.responses.create.return_value = MagicMock(
        output_text="not json",
        model="gpt-4o-mini",
        id="resp-bad",
        usage=MagicMock(input_tokens=1, output_tokens=1, total_tokens=2),
    )

    with patch("app.services.llm_client._client", return_value=mock_client):
        r = call_chat_turn_structured([{"role": "user", "content": "hi"}])

    assert not r.ok
    assert r.error is not None


def test_llm_disabled_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config.settings, "llm_provider", "openai")
    monkeypatch.setattr(app_config.settings, "openai_api_key", None)
    monkeypatch.setattr(app_config.settings, "gemini_api_key", None)
    r = call_chat_turn_structured([{"role": "user", "content": "hi"}])
    assert not r.ok
    assert "OPENAI_API_KEY" in (r.error or "")


def test_gemini_compat_base_url_uses_json_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config.settings, "llm_provider", "openai")
    monkeypatch.setattr(app_config.settings, "openai_api_key", "test-gemini-key")
    monkeypatch.setattr(
        app_config.settings,
        "openai_base_url",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=_valid_payload()))],
        model="gemini-2.0-flash",
        id="resp-gem",
        usage=MagicMock(prompt_tokens=1, completion_tokens=2, total_tokens=3),
    )

    with patch("app.services.llm_client._client", return_value=mock_client):
        r = call_chat_turn_structured([{"role": "user", "content": "hi"}])

    assert r.ok
    kw = mock_client.chat.completions.create.call_args.kwargs
    assert kw["response_format"] == {"type": "json_object"}
    assert r.api_type == "chat_completions_fallback"


def test_responses_fallback_to_chat_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config.settings, "llm_provider", "openai")
    monkeypatch.setattr(app_config.settings, "openai_api_key", "sk-test-key")
    monkeypatch.setattr(app_config.settings, "openai_base_url", None)

    mock_client = MagicMock()
    mock_client.responses.create.side_effect = RuntimeError("responses path unavailable")
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=_valid_payload()))],
        model="gpt-4o-mini",
        id="cmp-fallback-1",
        usage=MagicMock(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    )
    with patch("app.services.llm_client._client", return_value=mock_client):
        r = call_chat_turn_structured([{"role": "user", "content": "hi"}])
    assert r.ok
    assert r.api_type == "chat_completions_fallback"
    assert r.fallback_reason is not None


def test_llm_disabled_gemini_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config.settings, "llm_provider", "gemini")
    monkeypatch.setattr(app_config.settings, "openai_api_key", "sk-should-not-use")
    monkeypatch.setattr(app_config.settings, "gemini_api_key", None)
    r = call_chat_turn_structured([{"role": "user", "content": "hi"}])
    assert not r.ok
    assert "GEMINI_API_KEY" in (r.error or "")
