"""应用配置：自环境变量 / .env 读取数据库、LLM、提示词目录与仿真开关。"""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import CONSENT_DOCUMENT_VERSION, DEFAULT_PROMPT_BUNDLE_VERSION


def _default_prompts_dir() -> Path:
    """默认指向仓库根目录下的 prompts/（本文件位于 apps/api/app，上溯两级到仓库根）。"""
    api_root = Path(__file__).resolve().parents[1]
    return api_root.parent.parent / "prompts"


DEFAULT_GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class Settings(BaseSettings):
    """全局单例配置；字段可由环境变量覆盖（见各 Field 的 validation_alias）。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://safechat:safechat@localhost:5432/safechat_aud"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    consent_document_version: str = CONSENT_DOCUMENT_VERSION
    prompts_dir: Path = Field(default_factory=_default_prompts_dir)
    prompt_bundle_version: str = DEFAULT_PROMPT_BUNDLE_VERSION

    # LLM_PROVIDER=openai|gemini：共用 OpenAI SDK；Gemini 走官方 OpenAI 兼容端点
    llm_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices("LLM_PROVIDER", "llm_provider"),
    )
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"

    gemini_api_key: str | None = None
    gemini_base_url: str = Field(default=DEFAULT_GEMINI_OPENAI_BASE_URL)
    gemini_model: str = Field(default="gemini-2.0-flash")

    llm_timeout_seconds: float = 45.0
    llm_max_retries: int = 2

    # 批量/离线评测：simulation_force_arm 可为三规范臂或旧 empathic|neutral
    simulation_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("SAFECHAT_SIMULATION_MODE", "simulation_mode"),
    )
    simulation_force_arm: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SAFECHAT_SIMULATION_FORCE_ARM", "simulation_force_arm"),
    )
    # three_arm：1:1:1 分配到 neutral_professional / supportive_practical / warm_empathic
    # two_arm_ac：仅 A 与 C（Neutral/Professional vs Warm/Empathic）
    randomization_mode: str = Field(
        default="three_arm",
        validation_alias=AliasChoices("SAFECHAT_RANDOMIZATION_MODE", "randomization_mode"),
    )


settings = Settings()
