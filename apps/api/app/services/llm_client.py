"""统一 LLM 适配：超时、重试、用量与延迟；不修改业务 FSM。

当前实现走 **Chat Completions** + ``response_format``（OpenAI 侧为 json_schema 或 json_object），
与 Structured Outputs 同级的 JSON 契约由 ``LlmTurnStructuredOutput`` / ``openai_json_schema_for_turn_output``
定义。若需切换 **Responses API**，应另增适配层并把 ``LLM_API_TYPE_LABEL`` 与审计字段同步更新。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.config import DEFAULT_GEMINI_OPENAI_BASE_URL, settings
from app.schemas.llm_turn_output import (
    LlmRawOpenAiShape,
    LlmTurnStructuredOutput,
    openai_json_schema_for_turn_output,
)


@dataclass
class LlmCallResult:
    """单次结构化聊天补全调用的结果：成功时含解析后输出与用量，失败时含错误信息。"""

    ok: bool
    parsed: LlmTurnStructuredOutput | None = None
    raw_json: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: int = 0
    model_version: str = ""
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    raw_content: str | None = None
    attempts: int = 1


def _llm_provider_norm() -> str:
    """规范化 LLM 提供方名称（openai / gemini）。"""
    return (settings.llm_provider or "openai").strip().lower()


def effective_llm_api_key() -> str:
    """当前 provider 下用于 OpenAI SDK 的密钥（Gemini 亦经兼容端点）。"""
    if _llm_provider_norm() == "gemini":
        return (settings.gemini_api_key or "").strip()
    return (settings.openai_api_key or "").strip()


def effective_llm_base_url() -> str | None:
    """当前提供方对应的 API base URL（Gemini 走兼容 OpenAI 端点时可非空）。"""
    if _llm_provider_norm() == "gemini":
        u = (settings.gemini_base_url or "").strip()
        return u or DEFAULT_GEMINI_OPENAI_BASE_URL
    u = (settings.openai_base_url or "").strip()
    return u or None


def effective_llm_model() -> str:
    """当前环境与提供方下的默认模型名。"""
    if _llm_provider_norm() == "gemini":
        return (settings.gemini_model or "gemini-2.0-flash").strip()
    return (settings.openai_model or "gpt-4o-mini").strip()


def llm_is_configured() -> bool:
    """是否已配置当前提供方所需 API Key（路由据此决定是否尝试 LLM）。"""
    return bool(effective_llm_api_key())


def _use_gemini_compat_response_mode() -> bool:
    """是否改用 json_object 而非 json_schema（Gemini 或 Google 兼容 base_url 时常需如此）。"""
    if _llm_provider_norm() == "gemini":
        return True
    base = (effective_llm_base_url() or "").lower()
    return "generativelanguage.googleapis.com" in base


def _client() -> OpenAI | None:
    """构造 OpenAI SDK 客户端；无 Key 时返回 None。"""
    key = effective_llm_api_key()
    if not key:
        return None
    kwargs: dict[str, Any] = {"api_key": key}
    base = effective_llm_base_url()
    if base:
        kwargs["base_url"] = base
    return OpenAI(**kwargs)


def _parse_structured_content(content: str) -> LlmTurnStructuredOutput:
    """将模型返回的 JSON 字符串解析并校验为 LlmTurnStructuredOutput。"""
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("LLM output is not a JSON object")
    raw = LlmRawOpenAiShape.model_validate(data)
    out = raw.to_canonical()
    return LlmTurnStructuredOutput.model_validate(out.model_dump())


def call_chat_turn_structured(messages: list[dict[str, str]]) -> LlmCallResult:
    """调用聊天补全并要求结构化 JSON；含超时重试；失败时 ok=False 供路由回退 stub。"""
    client = _client()
    if client is None:
        prov = _llm_provider_norm()
        hint = "GEMINI_API_KEY" if prov == "gemini" else "OPENAI_API_KEY"
        return LlmCallResult(
            ok=False,
            error=f"LLM disabled: no API key for provider={prov} (set {hint})",
            model_version="",
        )

    spec = openai_json_schema_for_turn_output()
    model = effective_llm_model()
    timeout = float(settings.llm_timeout_seconds)
    max_retries = max(0, int(settings.llm_max_retries))
    total_attempts = 0
    last_err: str | None = None
    t0 = time.perf_counter()
    gemini_json_object = _use_gemini_compat_response_mode()

    for attempt in range(max_retries + 1):
        total_attempts = attempt + 1
        try:
            if gemini_json_object:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=timeout,
                    response_format={"type": "json_object"},
                )
            else:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=timeout,
                    response_format={
                        "type": "json_schema",
                        "json_schema": spec,
                    },
                )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            msg = completion.choices[0].message
            content = (msg.content or "").strip()
            if not content:
                raise ValueError("empty model content")

            parsed = _parse_structured_content(content)
            usage = completion.usage
            inp = getattr(usage, "prompt_tokens", None) if usage else None
            out_t = getattr(usage, "completion_tokens", None) if usage else None
            tot = getattr(usage, "total_tokens", None) if usage else None

            raw_dict = json.loads(content)
            return LlmCallResult(
                ok=True,
                parsed=parsed,
                raw_json=raw_dict if isinstance(raw_dict, dict) else None,
                latency_ms=latency_ms,
                model_version=str(completion.model or model),
                response_id=str(completion.id) if completion.id else None,
                input_tokens=inp,
                output_tokens=out_t,
                total_tokens=tot,
                raw_content=content[:20000],
                attempts=total_attempts,
            )
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt >= max_retries:
                break
            time.sleep(0.4 * (attempt + 1))
        except APIStatusError as e:
            last_err = f"APIStatusError: {e.status_code} {e.message}"
            if e.status_code in (429, 500, 502, 503) and attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            break
        except (json.JSONDecodeError, ValueError) as e:
            last_err = f"parse_error: {e}"
            break
        except Exception as e:  # pragma: no cover - defensive
            last_err = f"{type(e).__name__}: {e}"
            break

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return LlmCallResult(
        ok=False,
        error=last_err or "unknown_llm_error",
        latency_ms=latency_ms,
        model_version=model,
        attempts=total_attempts,
    )
