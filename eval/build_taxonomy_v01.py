#!/usr/bin/env python3
"""
从批量输出目录读取前 N 条 artifact（含 turns），汇总 failure taxonomy v0.1。
用法：python eval/build_taxonomy_v01.py --batch-dir eval/output/qa_real_llm_cycle1 --first-n 20
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(REPO_ROOT))

from eval.graders import grade_session


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-dir", type=Path, required=True)
    ap.add_argument("--first-n", type=int, default=20)
    args = ap.parse_args()

    summary_path = args.batch_dir / "summary.jsonl"
    if not summary_path.is_file():
        print("Missing summary.jsonl", file=sys.stderr)
        return 2

    lines = summary_path.read_text(encoding="utf-8").strip().split("\n")
    rows = [json.loads(x) for x in lines if x.strip()][: args.first_n]

    taxonomy_counts: dict[str, int] = defaultdict(int)
    taxonomy_examples: dict[str, list[str]] = defaultdict(list)

    def add_example(key: str, run_slug: str) -> None:
        if len(taxonomy_examples[key]) < 5 and run_slug not in taxonomy_examples[key]:
            taxonomy_examples[key].append(run_slug)

    per_run: list[dict[str, Any]] = []

    for row in rows:
        run_slug = f"{row['persona_id']}__{row['arm']}__r{row['run_index']}"
        art_path = args.batch_dir / "artifacts" / f"{run_slug}.json"
        if not art_path.is_file():
            print(f"Missing artifact: {art_path}", file=sys.stderr)
            return 2
        art = json.loads(art_path.read_text(encoding="utf-8"))
        turns = art.get("turns") or []
        arm = str(row.get("arm") or art.get("arm") or "")
        g = grade_session(arm=arm, turns=turns)

        flags: list[str] = []

        if g["style_leakage"]["violation"]:
            taxonomy_counts["F1_style_leakage_neutral"] += 1
            add_example("F1_style_leakage_neutral", run_slug)
            flags.append("F1")

        oq = g["one_question"]
        if oq["violation_count"] > 0:
            taxonomy_counts["F2_multi_question_turn"] += 1
            add_example("F2_multi_question_turn", run_slug)
            flags.append("F2")

        s3 = g["stage3_plan"]
        if s3.get("violation"):
            taxonomy_counts["F3_stage3_vague_micro_plan"] += 1
            add_example("F3_stage3_vague_micro_plan", run_slug)
            flags.append("F3")

        stc = int(row.get("stub_turns_count") or 0)
        if row.get("llm_attempted") and 0 < stc < 9:
            taxonomy_counts["F4_partial_stub_mixed_llm"] += 1
            add_example("F4_partial_stub_mixed_llm", run_slug)
            flags.append("F4")

        if row.get("llm_attempted") and stc >= 9:
            taxonomy_counts["F6_full_session_stub_or_llm_disabled"] += 1
            add_example("F6_full_session_stub_or_llm_disabled", run_slug)
            flags.append("F6")

        if not row.get("completed_all_stages"):
            taxonomy_counts["F5_incomplete_session"] += 1
            add_example("F5_incomplete_session", run_slug)
            flags.append("F5")

        per_run.append({"run_slug": run_slug, "flags": flags, "graders": g})

    out_json = {
        "taxonomy_version": "0.1",
        "batch_dir": str(args.batch_dir),
        "first_n": args.first_n,
        "sessions_analyzed": len(rows),
        "counts_by_type": dict(sorted(taxonomy_counts.items(), key=lambda x: -x[1])),
        "example_run_slugs": {k: v for k, v in sorted(taxonomy_examples.items())},
        "per_run_summary": per_run,
    }
    jpath = args.batch_dir / "failure_taxonomy_v01.json"
    jpath.write_text(json.dumps(out_json, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Failure taxonomy v0.1",
        "",
        f"- Batch directory: `{args.batch_dir}`",
        f"- Sessions analyzed: {len(rows)}",
        "",
        "## Counts by type (desc)",
        "",
        "| Type | Count | Example run_slug |",
        "|------|------|----------------|",
    ]
    for k, c in sorted(taxonomy_counts.items(), key=lambda x: -x[1]):
        ex = ", ".join(taxonomy_examples.get(k, [])[:3])
        md_lines.append(f"| {k} | {c} | {ex} |")
    md_lines += [
        "",
        "## Type descriptions",
        "",
        "- **F1_style_leakage_neutral**: warm/relational wording detected in neutral arm.",
        "- **F2_multi_question_turn**: two-plus question marks or explicit parallel asks in one turn.",
        "- **F3_stage3_vague_micro_plan**: stage_after=3 assistant text lacks if-then/concrete action cues.",
        "- **F4_partial_stub_mixed_llm**: partial stub fallback across 9 turns (e.g., JSON/timeout issues), verify with llm_calls.",
        "- **F5_incomplete_session**: session did not complete all stages.",
        "- **F6_full_session_stub_or_llm_disabled**: 9/9 turns were stub; common causes are quota/key/network or LLM disabled.",
        "",
        f"Machine-readable: `{jpath.name}`",
    ]
    (args.batch_dir / "failure_taxonomy_v01.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Wrote {jpath} and failure_taxonomy_v01.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
