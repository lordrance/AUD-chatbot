#!/usr/bin/env python3
"""
端到端烟测：同意 → 资格 → 基线 → 随机化 → 全阶段聊天（含 Stage1 反馈卡 continue）
→ 校验会话摘要 → 提交后测 → 校验 completed。

依赖：已启动 FastAPI（默认 http://127.0.0.1:8000）、PostgreSQL 已迁移、可选 LLM（未配置则走 stub）。

用法（仓库根目录）:
  pip install httpx   # 或与 apps/api 共用虚拟环境
  python scripts/e2e-smoke.py
  set E2E_API_BASE=http://127.0.0.1:8000 && python scripts/e2e-smoke.py
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx

DEFAULT_BASE = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8000").rstrip("/")

# 按 FSM 槽位顺序：每轮 user 文本填满「当前第一个缺失槽」（ neutral 内容，避免安全闸误触发）
CHAT_TURNS: list[str] = [
    # Stage 0
    "烟测参与者",
    "是的，我已阅读说明并准备好开始。",
    # Stage 1
    "通常工作日晚上会喝 2 杯啤酒，周末有时多一点。",
    "最近一次喝多是在朋友聚会，第二天早上起来不舒服。",
    "主要是为了睡眠更好，也想减少第二天的迟钝感。",
    "7",
    "6",
    # Stage 2（Stage1 反馈后继续）
    "压力大且一个人在家无聊的晚上。",
    "家里客厅。",
    "通常是晚上九点后。",
    "我一个人。",
    "有点烦躁又有点空虚。",
    "看到茶几上剩的啤酒就会想喝。",
    # Stage 3（final_confidence 用 8，避免触发缩小路径）
    "先离开现场去散步十分钟",
    "如果我想喝，我就先穿上外套出门走 10 分钟，然后再决定是否还要喝。",
    "可能会懒得动或觉得麻烦。",
    "先在门口放好运动鞋并把音乐列表打开，降低启动成本。",
    "8",
    # Stage 4
    "归根到底是想睡好一点、第二天更清晰。",
    "最容易是在无聊且独自在家的晚上。",
    "用出门散步 10 分钟代替先开冰箱。",
    "7",
    "带走的核心一句：先把环境线索切断一小步。",
]


def _die(msg: str, detail: Any = None) -> None:
    print(f"[e2e-smoke] FAIL: {msg}", file=sys.stderr)
    if detail is not None:
        print(detail, file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    base = DEFAULT_BASE
    client = httpx.Client(base_url=base, timeout=120.0)
    try:
        _run_smoke(client)
    finally:
        client.close()


def _run_smoke(client: httpx.Client) -> None:
    # 1) 同意书版本
    r = client.get("/api/v1/consent-document")
    if r.status_code != 200:
        _die(f"consent-document -> {r.status_code}", r.text)
    consent_version = r.json()["consent_document_version"]

    # 2) 创建会话
    r = client.post("/api/v1/sessions")
    if r.status_code != 201:
        _die(f"POST /sessions -> {r.status_code}", r.text)
    created = r.json()
    session_id = created["session_id"]
    token = created["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"[e2e-smoke] session_id={session_id}")

    def sget(path: str) -> dict[str, Any]:
        rr = client.get(path, headers=headers)
        if rr.status_code != 200:
            _die(f"GET {path} -> {rr.status_code}", rr.text)
        data = rr.json()
        assert isinstance(data, dict)
        return data

    def spost(path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        rr = client.post(path, headers=headers, json=json)
        if rr.status_code not in (200, 201):
            _die(f"POST {path} -> {rr.status_code}", rr.text)
        data = rr.json()
        assert isinstance(data, dict)
        return data

    # 3) 同意
    spost(
        f"/api/v1/sessions/{session_id}/consent",
        {"consent_accepted": True, "consent_document_version": consent_version},
    )

    # 4) 资格（男性 AUDIT-C 总分需 ≥4）
    body_elig = {
        "age_years": 30,
        "sex_at_birth": "male",
        "audit_c_frequency": 2,
        "audit_c_typical_quantity": 1,
        "audit_c_binge": 1,
        "wants_to_reduce_drinking": True,
        "crisis_seeking_emergency_help_now": False,
        "crisis_unable_to_complete_severe_distress": False,
        "crisis_needs_immediate_medical_or_clinical": False,
    }
    r = client.post(
        f"/api/v1/sessions/{session_id}/eligibility",
        headers=headers,
        json=body_elig,
    )
    if r.status_code != 200:
        _die(f"POST eligibility -> {r.status_code}", r.text)
    elig = r.json()
    if not elig.get("passed", True):
        _die("eligibility not passed", elig)

    # 5) 基线（开放题保持中性，避免聊前安全闸拦截）
    spost(
        f"/api/v1/sessions/{session_id}/surveys/baseline",
        {
            "typical_drinks_last_week": 6.0,
            "readiness_to_change_1_10": 6,
            "importance_to_reduce_0_10": 7,
            "prior_chatbot_or_ai_use": "rarely",
            "in_treatment_for_aud_or_mental_health": False,
            "treatment_notes": None,
            "education_level": "college_grad",
            "employment_status": "employed",
            "primary_concern_short": "希望减少饮酒并改善睡眠与白天的精力。",
        },
    )

    # 6) 随机化
    rz = spost(f"/api/v1/sessions/{session_id}/randomize", {})
    if not rz.get("arm"):
        _die("randomize missing arm", rz)
    print(f"[e2e-smoke] randomized arm={rz['arm']!r}")

    # 7) 聊天 + Stage1 反馈 continue
    turn_idx = 0
    for step in range(80):
        state = sget(f"/api/v1/sessions/{session_id}/state")
        status = state["status"]

        if status == "post_survey_pending":
            print(f"[e2e-smoke] chat finished after {turn_idx} user turns (loop step {step}).")
            break

        if status == "stage1_feedback_pending":
            cont = spost(f"/api/v1/sessions/{session_id}/chat/stage1-feedback/continue", {})
            print(f"[e2e-smoke] stage1_feedback_continue exchange_index={cont.get('exchange_index')}")
            continue

        if status not in ("chat_ready", "chat_active"):
            _die(f"unexpected status before chat turn: {status!r}", state)

        if turn_idx >= len(CHAT_TURNS):
            _die(f"need more CHAT_TURNS; stuck at step {step} status={status!r}", state)

        text = CHAT_TURNS[turn_idx]
        r = client.post(
            f"/api/v1/sessions/{session_id}/chat/turn",
            headers=headers,
            json={"text": text},
        )
        if r.status_code != 200:
            _die(f"chat turn {turn_idx} -> {r.status_code}", r.text)
        ct = r.json()
        turn_idx += 1
        print(
            f"[e2e-smoke] turn {turn_idx}: stage_after={ct.get('stage_after')} "
            f"status_after={ct.get('status_after')} closed={ct.get('chat_closed')} "
            f"stub={ct.get('stub')}"
        )
    else:
        st = sget(f"/api/v1/sessions/{session_id}/state")
        _die("chat did not reach post_survey_pending within step limit", st)

    # 8) 摘要（GET state）
    state = sget(f"/api/v1/sessions/{session_id}/state")
    if state["status"] != "post_survey_pending":
        _die("expected post_survey_pending after chat", state)
    summary = state.get("chat_summary")
    if not isinstance(summary, dict) or not summary.get("schema_version"):
        _die("chat_summary missing or invalid", summary)
    print(f"[e2e-smoke] chat_summary schema_version={summary.get('schema_version')!r}")

    # 9) 后测
    post_body: dict[str, Any] = {f"wai_tech_sf_item_{i:02d}": 4 for i in range(1, 13)}
    post_body.update(
        {
            "trust_1_5": 4,
            "helpfulness_1_5": 4,
            "disclosure_comfort_1_5": 4,
            "change_intention_1_5": 4,
            "manipulation_felt_warm_1_5": 4,
            "manipulation_felt_professional_1_5": 4,
            "manipulation_felt_practical_actionable_1_5": 4,
            "manipulation_understood_feelings_1_5": 4,
            "manipulation_felt_repetitive_1_5": 3,
            "manipulation_felt_personal_tailored_1_5": 4,
            "open_most_helpful": "烟测：结构化的提问让我一步步想清楚。",
            "open_unnatural_or_uncomfortable": "烟测：暂无明显不适。",
        }
    )
    done = spost(f"/api/v1/sessions/{session_id}/surveys/post", post_body)
    if done.get("status") != "completed":
        _die("post survey did not complete session", done)

    final = sget(f"/api/v1/sessions/{session_id}/state")
    if final["status"] != "completed":
        _die("expected completed after post survey", final)

    print("[e2e-smoke] OK: randomize → chat → summary → post_survey → completed")


if __name__ == "__main__":
    try:
        main()
    except httpx.ConnectError as exc:
        _die(
            "无法连接 API。默认地址为 "
            f"{DEFAULT_BASE!r}（可用环境变量 E2E_API_BASE 覆盖）；"
            "请先启动后端并确保数据库已迁移（apps/api 下 uvicorn 等）。",
            exc,
        )
