#!/usr/bin/env python3
"""
无 PostgreSQL 时仍可用真实 OpenAI 跑满 FSM 对话（与线上同一套 slot 推进、compose、structured LLM）。
用于 QA 批次；正式集成仍以 `run_batch.py` + DATABASE_URL 为准。

用法（仓库根目录）：
  set OPENAI_API_KEY=...
  apps\\api\\.venv\\Scripts\\python.exe eval/run_llm_offline_batch.py --output eval/output/qa_real_llm_cycle1
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

EXPECTED_CHAT_USER_TURNS = 25
_DEFAULT_TURNS: list[str] = [
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


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_personas(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("personas") or []


def main() -> int:
    parser = argparse.ArgumentParser(description="离线 FSM + 真实 LLM 批量转写（无 DB）")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs-per-arm", type=int, default=2)
    parser.add_argument("--personas", type=Path, default=EVAL_DIR / "personas.yaml")
    parser.add_argument("--prompt-bundle-version", type=str, default="0.2.1")
    parser.add_argument(
        "--limit-runs",
        type=int,
        default=0,
        help="最多跑多少条 session（0=不限制；用于试跑）",
    )
    parser.add_argument(
        "--persona-start",
        type=int,
        default=0,
        help="从 personas 列表中的索引开始（含），用于续跑后半批",
    )
    parser.add_argument(
        "--persona-end",
        type=int,
        default=None,
        help="personas 结束索引（不含）；默认到列表末尾",
    )
    args = parser.parse_args()

    os.environ["PROMPT_BUNDLE_VERSION"] = args.prompt_bundle_version
    sys.path.insert(0, str(API_ROOT))
    sys.path.insert(0, str(REPO_ROOT))

    from app.config import settings
    from app.services.llm_client import effective_llm_model, llm_is_configured

    if not llm_is_configured():
        prov = (settings.llm_provider or "openai").strip().lower()
        need = "GEMINI_API_KEY" if prov == "gemini" else "OPENAI_API_KEY"
        print(f"需要环境变量 {need}（当前 LLM_PROVIDER={prov}）", file=sys.stderr)
        return 2
    from app.services.prompt_registry import clear_bundle_cache, load_bundle
    from eval.fsm_turn_local import LocalChatState, apply_user_turn_local
    from eval.heuristics import analyze_run

    clear_bundle_cache()
    bundle = load_bundle(None)
    if bundle.version_ref != f"safechat-aud@{args.prompt_bundle_version}":
        print(
            f"警告：期望 safechat-aud@{args.prompt_bundle_version}，实际 {bundle.version_ref}",
            file=sys.stderr,
        )

    out_root = args.output
    transcripts_dir = out_root / "transcripts"
    artifacts_dir = out_root / "artifacts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    personas = _load_personas(args.personas)
    pe = args.persona_end if args.persona_end is not None else len(personas)
    personas = personas[args.persona_start : pe]
    if not personas:
        print("persona 切片为空", file=sys.stderr)
        return 2
    arms = ("empathic", "neutral")
    summary_rows: list[dict[str, Any]] = []
    csv_fieldnames: list[str] | None = None
    failure_jsonl = out_root / "failure_log.jsonl"
    failure_jsonl.unlink(missing_ok=True)

    model_fixed = effective_llm_model()
    prov = (settings.llm_provider or "openai").strip().lower()
    manifest = {
        "kind": "safechat_llm_offline_batch",
        "started_at": _utc_stamp(),
        "prompt_bundle_ref": bundle.version_ref,
        "llm_provider": prov,
        "effective_llm_model": model_fixed,
        "openai_model": (settings.openai_model or "").strip(),
        "gemini_model": (settings.gemini_model or "").strip(),
        "openai_base_url_set": bool((settings.openai_base_url or "").strip()),
        "runs_per_arm": args.runs_per_arm,
        "persona_count": len(personas),
        "limit_runs": args.limit_runs,
        "note": "无 DB；与 run_batch.py 产物结构对齐，便于 taxonomy / 人工评审。",
    }
    (out_root / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    run_count = 0
    stop = False
    for persona in personas:
        if stop:
            break
        pid = persona["id"]
        for arm in arms:
            if stop:
                break
            for run_idx in range(args.runs_per_arm):
                if args.limit_runs and run_count >= args.limit_runs:
                    stop = True
                    break
                state = LocalChatState()
                dialogue: list[tuple[str, str]] = []
                transcript_turns: list[dict[str, Any]] = []
                stub_turns = 0
                invalid_json = 0
                last_model = model_fixed
                completed_all_stages = False

                user_turns = list(persona.get("user_turns") or [])
                if len(user_turns) != EXPECTED_CHAT_USER_TURNS:
                    print(
                        f"警告: persona {pid} user_turns={len(user_turns)}，需要 {EXPECTED_CHAT_USER_TURNS}；使用默认序列",
                        file=sys.stderr,
                    )
                    user_turns = _DEFAULT_TURNS

                for user_line in user_turns:
                    state, rec = apply_user_turn_local(
                        state=state,
                        arm=arm,
                        user_message=user_line,
                        bundle=bundle,
                        llm_attempted=True,
                        dialogue=dialogue,
                    )
                    if rec.get("stub"):
                        stub_turns += 1
                    if rec.get("llm_error"):
                        em = str(rec["llm_error"]).lower()
                        if any(k in em for k in ("json", "parse", "schema", "invalid", "decode")):
                            invalid_json += 1
                    if rec.get("llm_model"):
                        last_model = rec["llm_model"]
                    transcript_turns.append(
                        {
                            "user_text": rec["user_text"],
                            "assistant_text": rec["assistant_text"],
                            "stub": rec["stub"],
                            "stage_after": rec["stage_after"],
                            "chat_closed": rec["chat_closed"],
                            "prompt_version": rec["prompt_version"],
                            "llm_error": rec.get("llm_error"),
                        }
                    )
                    completed_all_stages = bool(rec.get("chat_closed"))

                run_slug = f"{pid}__{arm}__r{run_idx}"
                transcript_path = transcripts_dir / f"{run_slug}.txt"
                lines: list[str] = []
                for i, t in enumerate(transcript_turns, start=1):
                    lines.append(f"### Turn {i}")
                    lines.append(f"USER: {t.get('user_text', '')}")
                    lines.append(f"ASSISTANT: {t.get('assistant_text', '')}")
                    lines.append("")
                transcript_path.write_text("\n".join(lines), encoding="utf-8")

                fake_sid = str(uuid.uuid4())
                artifact = {
                    "persona_id": pid,
                    "arm": arm,
                    "run_index": run_idx,
                    "session_id": fake_sid,
                    "offline_batch": True,
                    "prompt_version": bundle.version_ref,
                    "model_version": last_model,
                    "completed_all_stages": completed_all_stages,
                    "fallback_used": stub_turns,
                    "invalid_json_count": invalid_json,
                    "final_slot_json": dict(state.slot_json or {}),
                    "transcript_path": str(transcript_path.relative_to(out_root)).replace("\\", "/"),
                    "stub_turns_count": stub_turns,
                    "llm_attempted": True,
                    "turns": transcript_turns,
                }
                (artifacts_dir / f"{run_slug}.json").write_text(
                    json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8"
                )

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
                    "session_id": fake_sid,
                    "prompt_version": bundle.version_ref,
                    **flags,
                }
                with failure_jsonl.open("a", encoding="utf-8") as ff:
                    ff.write(json.dumps(failure_row, ensure_ascii=False) + "\n")

                summary_row = {**artifact}
                summary_row.pop("turns", None)
                summary_rows.append(summary_row)
                run_count += 1

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

    summary_jsonl = out_root / "summary.jsonl"
    with summary_jsonl.open("w", encoding="utf-8") as sf:
        for row in summary_rows:
            sf.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary_csv = out_root / "summary.csv"
    with summary_csv.open("w", encoding="utf-8", newline="") as cf:
        writer = csv.DictWriter(cf, fieldnames=csv_fieldnames or [])
        writer.writeheader()
        for row in summary_rows:
            w = dict(row)
            w["final_slot_json"] = json.dumps(w["final_slot_json"], ensure_ascii=False)
            writer.writerow({k: w.get(k, "") for k in (csv_fieldnames or [])})

    manifest["finished_at"] = _utc_stamp()
    manifest["sessions_completed"] = len(summary_rows)
    (out_root / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"完成：{out_root}（{len(summary_rows)} sessions）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
