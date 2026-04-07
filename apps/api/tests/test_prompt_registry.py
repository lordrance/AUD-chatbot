import pytest

import app.config as app_config
from app.services.prompt_registry import PromptBundle, clear_bundle_cache, load_bundle


@pytest.fixture(autouse=True)
def _prompt_bundle_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """避免本机 .env 中 PROMPT_BUNDLE_VERSION 与仓库默认不一致导致断言失败。"""
    monkeypatch.setattr(app_config.settings, "prompt_bundle_version", "0.2.1")
    clear_bundle_cache()
    yield
    clear_bundle_cache()


def test_load_default_bundle() -> None:
    b = load_bundle(None)
    assert isinstance(b, PromptBundle)
    assert b.bundle_id == "safechat-aud"
    assert b.version == "0.2.1"
    assert b.version_ref == "safechat-aud@0.2.1"
    assert "notes" in b.global_data or "product" in b.global_data
    assert b.stages[0]["warm"]["slots"]["preferred_name"]
    assert b.stages[0]["warm"]["slots"]["orientation_ack"]
    assert b.supportive_practical.get("style") == "supportive_practical"
    assert b.stages[0]["supportive_practical"]["slots"]["preferred_name"]


def test_load_by_version_only() -> None:
    b = load_bundle("0.1")
    assert b.version_ref == "safechat-aud@0.1"
    b2 = load_bundle("0.2")
    assert b2.version_ref == "safechat-aud@0.2"
    b21 = load_bundle("0.2.1")
    assert b21.version_ref == "safechat-aud@0.2.1"
