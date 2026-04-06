# 首轮真实 Prompt QA — 人工评审说明（前 20 条）

## 批次与模型

- **输出目录**：`eval/output/qa_real_llm_cycle1/`（本机已生成 20 条 session，其余 40 条可在配额恢复后补跑）。
- **提示词包（该次运行）**：`safechat-aud@0.2`（见 `run_manifest.json`）。
- **模型（计划）**：`gpt-4o-mini`（见 `run_manifest.json`）。
- **重要**：本次执行时 OpenAI 返回 **429 配额用尽**，9/9 轮均为 **stub 回退**；`failure_taxonomy_v01` 中 **F6** 即描述该模式。配额恢复后请重跑离线或 TestClient 批次以得到真实 `assistant_text`。

## 评审怎么用表格

1. 打开 **`qa_cycle1_first20_human_plus_auto.csv`**（已预填自动评分列）。
2. 对照 **`transcripts/<run_slug>.txt`** 与 **`artifacts/<run_slug>.json`**（含 `turns` 与 `stage_after`）。
3. 按 **`TRANSCRIPT_REVIEW_RUBRIC.md`** 填 1–5 分人类列；自动列仅作筛选提示，**以人工为准**。

## 自动列含义

| 列 | 说明 |
|----|------|
| `auto_style_leakage` | `eval/graders.py`：neutral 臂温情用语命中 |
| `auto_oneq_violation_count` / `auto_oneq_score` | 去掉 probe 尾段后统计多问句 |
| `auto_stage3_violation` / `auto_stage3_score` | `stage_after==3` 轮次的 if-then / 具体行为词启发式 |
| `taxonomy_flags` | `build_taxonomy_v01.py` 汇总标签 |

## 产物索引

- `failure_taxonomy_v01.md` / `.json`：前 20 条上的 **failure taxonomy v0.1**
- `eval/GRADERS.md`：三类 grader 契约说明
