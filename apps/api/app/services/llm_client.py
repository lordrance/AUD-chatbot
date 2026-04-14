"""统一 LLM 适配：Responses API 主路径 + Chat Completions 回退。"""

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
    api_type: str = "chat_completions"
    previous_response_id: str | None = None
    finish_reason: str | None = None
    retry_count: int = 0
    refusal_flag: bool = False
    fallback_reason: str | None = None


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


def llm_endpoint_hang_risk() -> bool:
    """部分 Google 兼容端点在当前 SDK 调用链下可能阻塞；遇到时应走 stub。"""
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


def _messages_to_responses_input(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """将 chat messages 转为 Responses API input 形状。"""
    out: list[dict[str, Any]] = []
    for m in messages:
        role = str(m.get("role") or "user")
        text = str(m.get("content") or "")
        out.append(
            {
                "role": role,
                "content": [{"type": "input_text", "text": text}],
            }
        )
    return out


def _extract_response_output_text(resp: Any) -> str:
    """从 Responses API 返回体提取文本 JSON 字符串。"""
    direct = getattr(resp, "output_text", None)
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    output = getattr(resp, "output", None) or []
    for item in output:
        content = getattr(item, "content", None) or []
        for c in content:
            txt = getattr(c, "text", None)
            if isinstance(txt, str) and txt.strip():
                return txt.strip()
    raise ValueError("empty responses output_text")


def _extract_responses_finish_reason(resp: Any) -> str | None:
    output = getattr(resp, "output", None) or []
    for item in output:
        fr = getattr(item, "finish_reason", None)
        if fr:
            return str(fr)
    return None


def _extract_responses_refusal(resp: Any) -> bool:
    output = getattr(resp, "output", None) or []
    for item in output:
        content = getattr(item, "content", None) or []
        for c in content:
            ctype = str(getattr(c, "type", "")).lower()
            if ctype == "refusal":
                return True
    return False


def _call_responses_once(
    client: OpenAI,
    *,
    model: str,
    timeout: float,
    spec: dict[str, Any],
    messages: list[dict[str, str]],
) -> Any:
    return client.responses.create(
        model=model,
        input=_messages_to_responses_input(messages),
        timeout=timeout,
        response_format={
            "type": "json_schema",
            "json_schema": spec,
        },
    )


def _call_chat_completions_once(
    client: OpenAI,
    *,
    model: str,
    timeout: float,
    spec: dict[str, Any],
    messages: list[dict[str, str]],
    gemini_json_object: bool,
) -> Any:
    if gemini_json_object:
        return client.chat.completions.create(
            model=model,
            messages=messages,
            timeout=timeout,
            response_format={"type": "json_object"},
        )
    return client.chat.completions.create(
        model=model,
        messages=messages,
        timeout=timeout,
        response_format={
            "type": "json_schema",
            "json_schema": spec,
        },
    )


def call_chat_turn_structured(messages: list[dict[str, str]]) -> LlmCallResult:
    """优先 Responses API；失败自动回退 Chat Completions。"""
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
    responses_last_err: str | None = None
    t0 = time.perf_counter()
    gemini_json_object = _use_gemini_compat_response_mode()

    # Primary transport selection:
    # - OpenAI native endpoint: Responses API primary, Chat Completions fallback.
    # - Gemini/OpenAI-compat endpoint: Chat Completions primary (Responses may hang/unsupported).
    use_responses_primary = not gemini_json_object
    if use_responses_primary:
        for attempt in range(max_retries + 1):
            total_attempts += 1
            try:
                resp = _call_responses_once(
                    client,
                    model=model,
                    timeout=timeout,
                    spec=spec,
                    messages=messages,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                content = _extract_response_output_text(resp)
                parsed = _parse_structured_content(content)
                usage = getattr(resp, "usage", None)
                inp = getattr(usage, "input_tokens", None) if usage else None
                out_t = getattr(usage, "output_tokens", None) if usage else None
                tot = getattr(usage, "total_tokens", None) if usage else None
                raw_dict = json.loads(content)
                rid = str(getattr(resp, "id", "") or "").strip() or None
                return LlmCallResult(
                    ok=True,
                    parsed=parsed,
                    raw_json=raw_dict if isinstance(raw_dict, dict) else None,
                    latency_ms=latency_ms,
                    model_version=str(getattr(resp, "model", "") or model),
                    response_id=rid,
                    previous_response_id=(
                        str(getattr(resp, "previous_response_id", "") or "")
                        if getattr(resp, "previous_response_id", None)
                        else None
                    ),
                    input_tokens=inp,
                    output_tokens=out_t,
                    total_tokens=tot,
                    raw_content=content[:20000],
                    attempts=total_attempts,
                    api_type="responses",
                    finish_reason=_extract_responses_finish_reason(resp),
                    refusal_flag=_extract_responses_refusal(resp),
                    retry_count=attempt,
                )
            except (APITimeoutError, APIConnectionError, RateLimitError) as e:
                responses_last_err = f"responses:{type(e).__name__}: {e}"
                if attempt >= max_retries:
                    break
                time.sleep(0.4 * (attempt + 1))
            except APIStatusError as e:
                responses_last_err = f"responses:APIStatusError: {e.status_code} {e.message}"
                if e.status_code in (429, 500, 502, 503) and attempt < max_retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                break
            except (json.JSONDecodeError, ValueError) as e:
                responses_last_err = f"responses:parse_error: {e}"
                break
            except Exception as e:  # pragma: no cover - defensive
                responses_last_err = f"responses:{type(e).__name__}: {e}"
                break
    else:
        responses_last_err = "responses:skipped_for_gemini_compat_endpoint"

    # Fallback: Chat Completions (json_schema/json_object).
    for attempt in range(max_retries + 1):
        total_attempts += 1
        try:
            completion = _call_chat_completions_once(
                client,
                model=model,
                timeout=timeout,
                spec=spec,
                messages=messages,
                gemini_json_object=gemini_json_object,
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
                api_type=("chat_completions_primary" if not use_responses_primary else "chat_completions_fallback"),
                retry_count=attempt,
                fallback_reason=responses_last_err,
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
        error=(f"{responses_last_err}; {last_err}" if responses_last_err and last_err else (last_err or responses_last_err or "unknown_llm_error")),
        latency_ms=latency_ms,
        model_version=model,
        attempts=total_attempts,
        api_type=("chat_completions_primary" if not use_responses_primary else "chat_completions_fallback"),
        fallback_reason=responses_last_err,
    )
