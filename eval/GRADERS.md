# 轻量自动评分器（v0）

实现：`eval/graders.py`。对单条 session 的 `turns` 列表（与 artifact 中结构一致，含 `arm`、`assistant_text`、`stage_after`）调用 `grade_session(arm=..., turns=...)`。

## 1. `grade_style_leakage`

- **用途**：neutral 臂是否出现温情/关系性模板（与 warm 操纵混淆）。
- **输出**：`violation: bool`，`matched_spans`（最多 3 段摘录），`score` 0 或 1。

## 2. `grade_one_question_at_a_time`

- **用途**：单轮是否实质只有一个提问焦点。
- **做法**：按臂将 `assistant_text` 按 `谢谢你愿意告诉我。`（empathic）或 `收到。`（neutral）取 **最后一段** 再统计 `?`/`？` 与并列追问正则。
- **输出**：`violation_turns`（含 `focus_preview`），`violation_count`，`score`（0–1，随违规轮占比衰减）。

## 3. `grade_stage3_micro_plan_specificity`

- **用途**：阶段 3 助手文案是否足够具体（微计划）。
- **做法**：筛选 `stage_after == 3` 的轮次，检测 if-then 模式、具体行为词；极短且无线索视为不具体。
- **输出**：`violation`，`vague_count`，`details`（逐轮），`score`。

## 与 taxonomy 的关系

`eval/build_taxonomy_v01.py` 聚合上述结果并映射到 **F1–F6**（见该脚本及 `failure_taxonomy_v01.md`）。
