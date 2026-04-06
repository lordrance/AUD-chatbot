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
    ap = argparse.ArgumentParser(description="冒烟批次摘要 Markdown")
    ap.add_argument("--batch-dir", type=Path, required=True)
    ap.add_argument(
        "--out-md",
        type=Path,
        default=None,
        help="写入 Markdown（默认 <batch-dir>/smoke_summary.md）",
    )
    args = ap.parse_args()
    root = args.batch_dir.resolve()
    if not root.is_dir():
        print(f"目录不存在: {root}", file=sys.stderr)
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
            "\n> **提示**：`fallback_used` 很高且 `stub_llm=false` 时，常见原因是 **Gemini/Google 429 配额** 或 API 错误；"
            "请在 DB 表 `llm_calls.error_message` 或路由返回的 `llm_error` 元数据中确认，非结构化 JSON 解析问题。\n"
        )

    lines: list[str] = [
        "# Gemini / LLM 冒烟摘要",
        "",
        f"- **批次目录**: `{root}`",
        f"- **sessions**: {n}",
        f"- **run_manifest**: `{manifest.get('llm_provider', '?')}` / model `{manifest.get('effective_llm_model', '?')}`",
        note_quota.rstrip(),
        "",
        "## 聚合指标",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| completed_all_stages | {completed} / {n} |",
        f"| fallback_used（总次数，跨轮累加） | {total_fb} |",
        f"| invalid_json_count（总次数） | {total_inv} |",
        f"| failure_log style_leakage（启发式） | {style_leaks} |",
        f"| failure_log weak_stage_3_micro_plan | {weak_plan} |",
        f"| 转写中「单轮 ≥2 问号」轮次数（粗判多问题） | {multi_q_turns} |",
        "",
        "## 说明",
        "",
        "启发式标记不能替代人工读 `transcripts/*.txt`；`failure_log.jsonl` 含逐条详情。",
        "",
    ]

    out = args.out_md or (root / "smoke_summary.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
