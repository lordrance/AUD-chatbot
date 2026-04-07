"""研究条件臂（三水平）：规范 arm 字符串与 PromptBundle 风格块映射；兼容旧 persisted 值 empathic/neutral。"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Literal

from app.config import settings

if TYPE_CHECKING:
    from app.services.prompt_registry import PromptBundle

StyleBlockKey = Literal["warm", "neutral", "supportive_practical"]

# 写入 DB / API 的规范名（answer2.pdf：Neutral / Supportive-Practical / Warm）
CANONICAL_ARMS: tuple[str, ...] = (
    "neutral_professional",
    "supportive_practical",
    "warm_empathic",
)


def canonicalize_arm(arm: str | None) -> str:
    """将历史 empathic/neutral 或已规范名统一为 neutral_professional / supportive_practical / warm_empathic。"""
    if not arm:
        return "neutral_professional"
    a = arm.strip()
    if a == "empathic":
        return "warm_empathic"
    if a == "neutral":
        return "neutral_professional"
    if a in CANONICAL_ARMS:
        return a
    return a


def style_block_key(arm: str | None) -> StyleBlockKey:
    """映射到 YAML 顶层风格键：warm / neutral / supportive_practical。"""
    c = canonicalize_arm(arm)
    if c == "warm_empathic":
        return "warm"
    if c == "supportive_practical":
        return "supportive_practical"
    return "neutral"


def arm_label_for_llm(arm: str | None) -> str:
    """供 LLM system 提示中的臂标签（英文）。"""
    c = canonicalize_arm(arm)
    return {
        "neutral_professional": "neutral_professional_A",
        "supportive_practical": "supportive_practical_B",
        "warm_empathic": "warm_empathic_C",
    }[c]


def style_dict_for_arm(bundle: "PromptBundle", arm: str | None) -> dict:
    """从 bundle 取全局风格 YAML dict。"""
    k = style_block_key(arm)
    if k == "warm":
        return bundle.warm
    if k == "supportive_practical":
        return bundle.supportive_practical
    return bundle.neutral


_FORCE_ARMS = frozenset(
    {
        "empathic",
        "neutral",
        "warm_empathic",
        "neutral_professional",
        "supportive_practical",
    },
)


def pick_random_arm() -> str:
    """按 randomization_mode 随机分配规范臂；simulation 下可强制。"""
    if settings.simulation_mode and settings.simulation_force_arm:
        fa = settings.simulation_force_arm.strip()
        if fa in _FORCE_ARMS:
            return canonicalize_arm(fa)
    mode = (settings.randomization_mode or "three_arm").strip().lower().replace("-", "_")
    if mode in ("two_arm_ac", "two_arm", "ac"):
        return "warm_empathic" if secrets.randbelow(2) == 0 else "neutral_professional"
    r = secrets.randbelow(3)
    return ("neutral_professional", "supportive_practical", "warm_empathic")[r]
