import json

from app.schemas.llm_turn_output import LlmRawOpenAiShape, LlmTurnStructuredOutput


def test_raw_to_canonical_roundtrip() -> None:
    raw = LlmRawOpenAiShape.model_validate(
        {
            "assistant_text": "  hello  ",
            "extracted_slot_entries": [{"key": "a", "value": "b"}],
            "stage_complete": False,
            "selected_strategy_ids": ["x"],
            "safety_level": 1,
            "needs_human_review": True,
        }
    )
    c = raw.to_canonical()
    assert isinstance(c, LlmTurnStructuredOutput)
    assert c.assistant_text == "hello"
    assert c.extracted_slots["a"] == "b"
    assert c.stage_complete is False


def test_openai_schema_is_object() -> None:
    from app.schemas.llm_turn_output import openai_json_schema_for_turn_output

    spec = openai_json_schema_for_turn_output()
    assert spec["name"] == "safechat_turn_output"
    assert spec["strict"] is True
    assert "assistant_text" in spec["schema"]["properties"]
