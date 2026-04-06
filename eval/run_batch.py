#!/usr/bin/env python3
"""
批量离线会话模拟：经 FastAPI TestClient 走完整 sessions/chat 逻辑。
用法见 eval/README.md。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = REPO_ROOT / "apps" / "api"
EVAL_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(EVAL_DIR))

from heuristics import analyze_run  # noqa: E402

# 与当前 FSM 必填槽位数一致（PDF 扩展后 25 轮）；persona user_turns 长度不符时回退到此序列
EXPECTED_CHAT_USER_TURNS = 25
DEFAULT_CHAT_USER_TURNS: list[str] = [
    "Alex",
    "I understand the study is not treatment.",
    "Yes, ready to start.",
    "About three times last week, a few drinks each time.",
    "Last Friday I drank more than I wanted.",
    "I want better sleep and mornings.",
    "8",
    "7",
    "After-work social pressure.",
    "Coworkers and clients.",
    "Restaurant or bar near work.",
    "Thursday and Friday evenings.",
    "Anxious and rushed.",
    "First round ordered for the table.",
    "After-work drinks with colleagues.",
    "delay_first_drink",
    "If it's a work dinner, I'll order water for the first round.",
    "I feel too tired to resist.",
    "I'll set a one-drink limit text to myself.",
    "8",
    "Better sleep and fewer rough mornings.",
    "After-work social drinking.",
    "If work dinner, water first then decide.",
    "8",
    "none",
]


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_session(client: Any, consent_version: str) -> tuple[str, str]:
    r = client.post("/api/v1/sessions")
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    token = r.json()["session_token"]
    h = _auth_headers(token)

    consent = {
        "consent_accepted": True,
        "consent_document_version": consent_version,
    }
    assert client.post(f"/api/v1/sessions/{sid}/consent", json=consent, headers=h).status_code == 200

    elig = {
        "age_years": 30,
        "sex_at_birth": "male",
        "audit_c_frequency": 3,
        "audit_c_typical_quantity": 2,
        "audit_c_binge": 2,
        "wants_to_reduce_drinking": True,
    }
    assert client.post(f"/api/v1/sessions/{sid}/eligibility", json=elig, headers=h).status_code == 200

    base = {
        "typical_drinks_last_week": 12,
        "readiness_to_change_1_10": 6,
        "importance_to_reduce_0_10": 7,
        "prior_chatbot_or_ai_use": "never",
        "in_treatment_for_aud_or_mental_health": False,
        "education_level": "college_grad",
        "employment_status": "employed",
    }
    assert client.post(f"/api/v1/sessions/{sid}/surveys/baseline", json=base, headers=h).status_code == 200

    return sid, token


def _randomize_forced(client: Any, settings_mod: Any, sid: str, token: str, arm: str) -> str:
    h = _auth_headers(token)
    settings_mod.simulation_mode = True
    settings_mod.simulation_force_arm = arm
    try:
        rz = client.post(f"/api/v1/sessions/{sid}/randomize", headers=h)
        assert rz.status_code == 200, rz.text
        got = rz.json()["arm"]
        assert got == arm, f"期望 arm={arm}，实际 {got}（请确认 simulation 开关生效）"
        return got
    finally:
        settings_mod.simulation_mode = False
        settings_mod.simulation_force_arm = None


def _load_personas(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("personas") or []


def _count_llm_metrics(db: Any, session_uuid: uuid.UUID) -> tuple[int, int, str | None]:
    from sqlalchemy import select

    from app.models.llm_call import LlmCall

    q = select(LlmCall).where(LlmCall.session_id == session_uuid).order_by(LlmCall.exchange_index.asc())
    rows = list(db.scalars(q).all())
    if not rows:
        return 0, 0, None

    fallback_used = sum(1 for r in rows if r.fallback_used)
    invalid_json = 0
    for r in rows:
        if r.success:
            continue
        em = (r.error_message or "").lower()
        if any(k in em for k in ("json", "parse", "schema", "invalid", "decode")):
            invalid_json += 1
    model_version = rows[-1].model_version or None
    return fallback_used, invalid_json, model_version


def _session_row(db: Any, session_uuid: uuid.UUID) -> Any:
    from sqlalchemy import select

    from app.models.session import SessionRecord

    return db.scalars(select(SessionRecord).where(SessionRecord.id == session_uuid)).one()


def _write_transcript(path: Path, turns: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i, t in enumerate(turns, start=1):
        lines.append(f"### Turn {i}")
        lines.append(f"USER: {t.get('user_text', '')}")
        lines.append(f"ASSISTANT: {t.get('assistant_text', '')}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="SafeChat-AUD 离线批量转写与 Prompt QA")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出目录（默认 eval/output/<UTC 时间戳>）",
    )
    parser.add_argument("--runs-per-arm", type=int, default=2, help="每个 persona 每臂重复次数（2–3 推荐）")
    parser.add_argument(
        "--max-personas",
        type=int,
        default=0,
        help="仅跑前 N 个 persona（0=不限制；用于冒烟等小批量）",
    )
    parser.add_argument("--personas", type=Path, default=EVAL_DIR / "personas.yaml")
    parser.add_argument("--persona-ids", nargs="*", default=None, help="仅跑指定 persona id")
    parser.add_argument(
        "--stub-llm",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="默认清空 OPENAI_API_KEY 走 stub；--no-stub-llm 使用环境变量中的真实密钥",
    )
    parser.add_argument(
        "--prompt-bundle-version",
        type=str,
        default=None,
        help="写入 PROMPT_BUNDLE_VERSION 后再导入 app（默认用 constants / 环境变量）",
    )
    args = parser.parse_args()

    if args.runs_per_arm < 1 or args.runs_per_arm > 5:
        print("runs-per-arm 建议 1–5", file=sys.stderr)
        return 2

    if args.max_personas < 0:
        print("--max-personas 须 >= 0", file=sys.stderr)
        return 2

    if not os.getenv("DATABASE_URL") and not os.getenv("TEST_DATABASE_URL"):
        print("请设置 DATABASE_URL（或 TEST_DATABASE_URL）指向已 migrate 的 PostgreSQL。", file=sys.stderr)
        return 2

    if args.prompt_bundle_version:
        os.environ["PROMPT_BUNDLE_VERSION"] = args.prompt_bundle_version.strip()

    # 在导入 app 前可选强制 stub
    if args.stub_llm:
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)

    from fastapi.testclient import TestClient

    import app.config as app_config
    from app.config import settings
    from app.services.llm_client import effective_llm_model, llm_is_configured
    from app.constants import CONSENT_DOCUMENT_VERSION
    from app.database import SessionLocal
    from app.main import app

    if args.stub_llm:
        app_config.settings.openai_api_key = None
        app_config.settings.gemini_api_key = None

    out_root = args.output or (EVAL_DIR / "output" / _utc_run_id())
    transcripts_dir = out_root / "transcripts"
    artifacts_dir = out_root / "artifacts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    prov = (settings.llm_provider or "openai").strip().lower()
    run_manifest = {
        "kind": "safechat_testclient_batch",
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prompt_bundle_version_env": os.getenv("PROMPT_BUNDLE_VERSION"),
        "llm_provider": prov,
        "effective_llm_model": effective_llm_model(),
        "openai_model": (settings.openai_model or ""),
        "gemini_model": (settings.gemini_model or ""),
        "stub_llm": bool(args.stub_llm),
        "runs_per_arm": args.runs_per_arm,
        "max_personas": args.max_personas,
    }
    (out_root / "run_manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary_jsonl = out_root / "summary.jsonl"
    summary_csv = out_root / "summary.csv"
    failure_jsonl = out_root / "failure_log.jsonl"
    failure_jsonl.unlink(missing_ok=True)

    personas = _load_personas(args.personas)
    if args.persona_ids:
        wanted = set(args.persona_ids)
        personas = [p for p in personas if p["id"] in wanted]
        missing = wanted - {p["id"] for p in personas}
        if missing:
            print(f"未找到 persona: {missing}", file=sys.stderr)
            return 2
    if args.max_personas > 0:
        personas = personas[: args.max_personas]

    arms = ("empathic", "neutral")
    csv_fieldnames: list[str] | None = None
    summary_rows: list[dict[str, Any]] = []

    client = TestClient(app)

    for persona in personas:
        pid = persona["id"]
        for arm in arms:
            for run_idx in range(args.runs_per_arm):
                sid_str, token = _bootstrap_session(client, CONSENT_DOCUMENT_VERSION)
                _randomize_forced(client, settings, sid_str, token, arm)
                h = _auth_headers(token)

                transcript_turns: list[dict[str, Any]] = []
                stub_turns = 0
                last_prompt_version: str | None = None
                completed_all_stages = False

                user_turns = list(persona.get("user_turns") or [])
                if len(user_turns) != EXPECTED_CHAT_USER_TURNS:
                    print(
                        f"警告: persona {pid} user_turns={len(user_turns)}，需要 {EXPECTED_CHAT_USER_TURNS}；使用默认序列",
                        file=sys.stderr,
                    )
                    user_turns = DEFAULT_CHAT_USER_TURNS

                for user_line in user_turns:
                    r = client.post(
                        f"/api/v1/sessions/{sid_str}/chat/turn",
                        json={"text": user_line},
                        headers=h,
                    )
                    assert r.status_code == 200, r.text
                    body = r.json()
                    if body.get("stub"):
                        stub_turns += 1
                    last_prompt_version = body.get("prompt_version") or last_prompt_version
                    transcript_turns.append(
                        {
                            "user_text": user_line,
                            "assistant_text": body.get("assistant_text") or "",
                            "stub": body.get("stub"),
                            "stage_after": body.get("stage_after"),
                            "chat_closed": body.get("chat_closed"),
                            "prompt_version": body.get("prompt_version"),
                        }
                    )
                    completed_all_stages = bool(body.get("chat_closed")) and body.get("status_after") == (
                        "post_survey_pending"
                    )

                session_uuid = uuid.UUID(sid_str)
                db = SessionLocal()
                try:
                    row = _session_row(db, session_uuid)
                    fb_db, inv_db, model_from_calls = _count_llm_metrics(db, session_uuid)
                    slot_json = dict(row.slot_json or {})
                    prompt_version = row.prompt_bundle_version or last_prompt_version or ""
                    model_version = model_from_calls or effective_llm_model()
                finally:
                    db.close()

                llm_attempted_globally = llm_is_configured()
                if llm_attempted_globally:
                    fallback_used = fb_db
                    invalid_json_count = inv_db
                else:
                    fallback_used = stub_turns
                    invalid_json_count = 0

                run_slug = f"{pid}__{arm}__r{run_idx}"
                transcript_path = transcripts_dir / f"{run_slug}.txt"
                _write_transcript(transcript_path, transcript_turns)

                artifact = {
                    "persona_id": pid,
                    "arm": arm,
                    "run_index": run_idx,
                    "session_id": sid_str,
                    "prompt_version": prompt_version,
                    "model_version": model_version,
                    "completed_all_stages": completed_all_stages,
                    "fallback_used": fallback_used,
                    "invalid_json_count": invalid_json_count,
                    "final_slot_json": slot_json,
                    "transcript_path": str(transcript_path.relative_to(out_root)).replace("\\", "/"),
                    "stub_turns_count": stub_turns,
                    "llm_attempted": llm_attempted_globally,
                    "turns": transcript_turns,
                }
                artifact_path = artifacts_dir / f"{run_slug}.json"
                artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")

                flags = analyze_run(
                    arm=arm,
                    completed_all_stages=completed_all_stages,
                    transcript_turns=transcript_turns,
                )
                failure_row = {
                    "run_slug": run_slug,
                    "persona_id": pid,
                    "arm": arm,
                    "run_index": run_idx,
                    "session_id": sid_str,
                    "prompt_version": prompt_version,
                    **flags,
                }

                summary_row = {**artifact, "transcript_path": artifact["transcript_path"]}
                summary_row.pop("turns", None)
                summary_rows.append(summary_row)

                with failure_jsonl.open("a", encoding="utf-8") as ff:
                    ff.write(json.dumps(failure_row, ensure_ascii=False) + "\n")

                flat_for_csv = dict(summary_row)
                flat_for_csv["final_slot_json"] = json.dumps(
                    flat_for_csv["final_slot_json"], ensure_ascii=False
                )
                if csv_fieldnames is None:
                    csv_fieldnames = list(flat_for_csv.keys())
                else:
                    for k in flat_for_csv:
                        if k not in csv_fieldnames:
                            csv_fieldnames.append(k)

    with summary_jsonl.open("w", encoding="utf-8") as sf:
        for row in summary_rows:
            wrow = dict(row)
            sf.write(json.dumps(wrow, ensure_ascii=False) + "\n")

    with summary_csv.open("w", encoding="utf-8", newline="") as cf:
        writer = csv.DictWriter(cf, fieldnames=csv_fieldnames or [])
        writer.writeheader()
        for row in summary_rows:
            w = dict(row)
            w["final_slot_json"] = json.dumps(w["final_slot_json"], ensure_ascii=False)
            writer.writerow({k: w.get(k, "") for k in (csv_fieldnames or [])})

    run_manifest["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_manifest["sessions_completed"] = len(summary_rows)
    (out_root / "run_manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"完成：{out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
