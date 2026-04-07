#!/usr/bin/env python3
"""从 run_batch / run_llm_offline_batch 输出目录生成简短冒烟摘要（Markdown）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _multi_question_heuristic(transcript_path: Path, batch_root: Path) -> int:
    """粗判：单轮助手文本中含 2 个及以上问号（非 ground truth）。"""
    p = batch_root / transcript_path
    if not p.is_file():
        return 0
    text = p.read_text(encoding="utf-8")
    hits = 0
    for block in text.split("### Turn"):
        if "ASSISTANT:" not in block:
            continue
        after = block.split("ASSISTANT:", 1)[1]
        if after.count("?") >= 2:
            hits += 1
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke batch summary Markdown")
    ap.add_argument("--batch-dir", type=Path, required=True)
    ap.add_argument(
        "--out-md",
        type=Path,
        default=None,
        help="Output Markdown path (default: <batch-dir>/smoke_summary.md)",
    )
    args = ap.parse_args()
    root = args.batch_dir.resolve()
    if not root.is_dir():
        print(f"Directory does not exist: {root}", file=sys.stderr)
        return 2

    summary = _load_jsonl(root / "summary.jsonl")
    failures = _load_jsonl(root / "failure_log.jsonl")
    manifest_path = root / "run_manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    n = len(summary)
    completed = sum(1 for r in summary if r.get("completed_all_stages"))
    total_fb = sum(int(r.get("fallback_used") or 0) for r in summary)
    total_inv = sum(int(r.get("invalid_json_count") or 0) for r in summary)

    style_leaks = sum(1 for r in failures if r.get("style_leakage"))
    weak_plan = sum(1 for r in failures if r.get("weak_stage_3_micro_plan"))
    multi_q_turns = 0
    for r in summary:
        tp = r.get("transcript_path") or ""
        if tp:
            multi_q_turns += _multi_question_heuristic(Path(tp), root)

    note_quota = ""
    if n > 0 and manifest.get("stub_llm") is False and total_fb >= n * 7:
        note_quota = (
            "\n> **Tip**: when `fallback_used` is high and `stub_llm=false`, the common cause is **Gemini/Google 429 quota** "
            "or API errors; check `llm_calls.error_message` or route-level `llm_error` metadata rather than JSON parsing.\n"
        )

    lines: list[str] = [
        "# Gemini / LLM Smoke Summary",
        "",
        f"- **Batch directory**: `{root}`",
        f"- **sessions**: {n}",
        f"- **run_manifest**: `{manifest.get('llm_provider', '?')}` / model `{manifest.get('effective_llm_model', '?')}`",
        note_quota.rstrip(),
        "",
        "## Aggregated Metrics",
        "",
        f"| Metric | Value |",
        f"|------|-----|",
        f"| completed_all_stages | {completed} / {n} |",
        f"| fallback_used (total count across turns) | {total_fb} |",
        f"| invalid_json_count (total count) | {total_inv} |",
        f"| failure_log style_leakage (heuristic) | {style_leaks} |",
        f"| failure_log weak_stage_3_micro_plan | {weak_plan} |",
        f"| transcript turns with >=2 question marks (rough multi-question heuristic) | {multi_q_turns} |",
        "",
        "## Notes",
        "",
        "Heuristic flags are not a substitute for manual review of `transcripts/*.txt`; see `failure_log.jsonl` for per-run details.",
        "",
    ]

    out = args.out_md or (root / "smoke_summary.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
