"""LLM 单轮结构化输出：Pydantic 校验；阶段跳转仅信服务端 FSM，模型 stage_complete 仅作记录。"""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class LlmTurnStructuredOutput(BaseModel):
    """规范化后的单轮模型输出（canonical 形态）。"""

    assistant_text: str = Field(min_length=1, max_length=4000)
    extracted_slots: dict[str, Any] = Field(default_factory=dict)
    stage_complete: bool = Field(
        description="模型推测；服务端将忽略此字段用于阶段跳转，仅记录。"
    )
    selected_strategy_ids: list[str] = Field(default_factory=list)
    safety_level: int = Field(ge=0, le=5)
    needs_human_review: bool

    @field_validator("assistant_text")
    @classmethod
    def strip_assistant(cls, v: str) -> str:
        """助手正文去首尾空白，空则校验失败。"""
        s = v.strip()
        if not s:
            raise ValueError("assistant_text empty")
        return s

    @field_validator("selected_strategy_ids", mode="before")
    @classmethod
    def coerce_strategy_ids(cls, v: Any) -> list[str]:
        """将策略 id 列表或单值统一为字符串列表。"""
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return [str(v)]


def openai_json_schema_for_turn_output() -> dict[str, Any]:
    """构造 OpenAI Chat Completions `response_format.json_schema`（strict）所需的 schema 描述。"""
    # 避免 dict[str, Any] 在 strict 下难以表达：extracted_slots 用键值对列表
    return {
        "name": "safechat_turn_output",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "assistant_text": {"type": "string"},
                "extracted_slot_entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["key", "value"],
                    },
                },
                "stage_complete": {"type": "boolean"},
                "selected_strategy_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "safety_level": {"type": "integer", "minimum": 0, "maximum": 5},
                "needs_human_review": {"type": "boolean"},
            },
            "required": [
                "assistant_text",
                "extracted_slot_entries",
                "stage_complete",
                "selected_strategy_ids",
                "safety_level",
                "needs_human_review",
            ],
        },
    }


class LlmRawOpenAiShape(BaseModel):
    """API 原始 JSON 形状（含 extracted_slot_entries 列表），可转为 LlmTurnStructuredOutput。"""

    assistant_text: str
    extracted_slot_entries: list[dict[str, Any]] = Field(default_factory=list)
    stage_complete: bool
    selected_strategy_ids: list[str] = Field(default_factory=list)
    safety_level: int = Field(ge=0, le=5)
    needs_human_review: bool

    def to_canonical(self) -> LlmTurnStructuredOutput:
        """将键值对列表折叠为 extracted_slots 字典并生成规范输出对象。"""
        slots: dict[str, Any] = {}
        for e in self.extracted_slot_entries:
            k = (e.get("key") or "").strip()
            if k:
                slots[k] = e.get("value") or ""
        return LlmTurnStructuredOutput(
            assistant_text=self.assistant_text,
            extracted_slots=slots,
            stage_complete=self.stage_complete,
            selected_strategy_ids=list(self.selected_strategy_ids),
            safety_level=self.safety_level,
            needs_human_review=self.needs_human_review,
        )
