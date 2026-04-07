"""LLM 单轮结构化输出：Pydantic 校验；阶段跳转仅信服务端 FSM；含 dialogue_acts / risk / next_action 供操纵检验与安全审计。"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class LlmRiskBlock(BaseModel):
    """模型自报风险层级（服务端仍以规则扫描为准）。"""

    level: int = Field(ge=0, le=5, description="0=no risk language in model view")
    reason: str | None = None


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
    dialogue_acts: list[str] = Field(
        default_factory=list,
        description="如 open_question, reflection, affirmation, summary, practical_suggestion",
    )
    next_action: Literal[
        "ask_followup",
        "offer_options",
        "move_stage",
        "show_resources",
    ] = "ask_followup"
    model_reported_stage: str | None = Field(
        default=None,
        description="模型自报 stage1|stage2|…；服务端 FSM 为准，仅作记录。",
    )
    risk: LlmRiskBlock = Field(default_factory=lambda: LlmRiskBlock(level=0, reason=None))

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

    @field_validator("dialogue_acts", mode="before")
    @classmethod
    def coerce_acts(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return [str(v)]


def openai_json_schema_for_turn_output() -> dict[str, Any]:
    """构造 OpenAI Chat Completions `response_format.json_schema`（strict）所需的 schema 描述。"""
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
                "dialogue_acts": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "next_action": {
                    "type": "string",
                    "enum": [
                        "ask_followup",
                        "offer_options",
                        "move_stage",
                        "show_resources",
                    ],
                },
                "model_reported_stage": {"type": ["string", "null"]},
                "risk": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "level": {"type": "integer", "minimum": 0, "maximum": 5},
                        "reason": {"type": ["string", "null"]},
                    },
                    "required": ["level", "reason"],
                },
            },
            "required": [
                "assistant_text",
                "extracted_slot_entries",
                "stage_complete",
                "selected_strategy_ids",
                "safety_level",
                "needs_human_review",
                "dialogue_acts",
                "next_action",
                "model_reported_stage",
                "risk",
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
    dialogue_acts: list[str] = Field(default_factory=list)
    next_action: str = "ask_followup"
    model_reported_stage: str | None = None
    risk: LlmRiskBlock | None = None

    def to_canonical(self) -> LlmTurnStructuredOutput:
        """将键值对列表折叠为 extracted_slots 字典并生成规范输出对象。"""
        slots: dict[str, Any] = {}
        for e in self.extracted_slot_entries:
            k = (e.get("key") or "").strip()
            if k:
                slots[k] = e.get("value") or ""
        na = self.next_action if self.next_action in (
            "ask_followup",
            "offer_options",
            "move_stage",
            "show_resources",
        ) else "ask_followup"
        rb = self.risk if self.risk is not None else LlmRiskBlock(level=0, reason=None)
        return LlmTurnStructuredOutput(
            assistant_text=self.assistant_text,
            extracted_slots=slots,
            stage_complete=self.stage_complete,
            selected_strategy_ids=list(self.selected_strategy_ids),
            safety_level=self.safety_level,
            needs_human_review=self.needs_human_review,
            dialogue_acts=list(self.dialogue_acts),
            next_action=na,  # type: ignore[arg-type]
            model_reported_stage=self.model_reported_stage,
            risk=rb,
        )
