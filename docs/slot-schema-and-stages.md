# Slot schema 与聊天阶段（严格对齐 answer2.pdf）

本文档冻结当前实验 instrument：三臂风格、Stage 0–4 槽位、策略库、摘要卡与审计口径。实现权威见 `apps/api/app/services/chat_fsm.py`、`apps/api/app/routers/sessions.py`、`apps/api/app/services/chat_summary.py`。

## 实验条件

- `arm`：`neutral_professional`（A）/ `supportive_practical`（B）/ `warm_empathic`（C）。
- 风格层：`prompts/neutral.yaml`、`prompts/supportive_practical.yaml`、`prompts/warm.yaml`。
- 随机化：`randomization_mode=three_arm|two_arm_ac`（`two_arm_ac`=A+C）。

## 阶段与槽位

| Stage | 目标 | 必填槽位（顺序） |
|------|------|------------------|
| 0 | 边界说明 + 就绪 | `preferred_name`, `ready_to_start` |
| 1 | 近期饮酒 + 动机 + 评分 | `recent_drinking_pattern`, `most_concerning_episode`, `top_reason_to_cut_down`, `importance_0_10`, `confidence_0_10` |
| 2 | 收敛一个关键情境 | `target_situation`, `where`, `when`, `who_with`, `emotion_or_state`, `immediate_trigger` |
| 3 | 策略与 if–then 计划 | `selected_strategy`, `if_then_plan`, `likely_obstacle`, `workaround`, `final_confidence_0_10`；若 `<7` 追加 `if_then_plan_revised`, `final_confidence_0_10_after_shrink` |
| 4 | 摘要卡收尾 | `summary_reason`, `summary_trigger`, `summary_plan`, `summary_confidence`, `optional_takeaway` |

说明：
- Stage 3 策略库固定 8 条，服务端每轮向模型暴露 `offered_strategy_ids`，上限 2 条。
- 阶段推进由服务端 FSM 决定；模型 `stage_complete` 仅审计用途。

## 存储与迁移

- `sessions.slot_json` 使用 `"{stage}:{slot}"` 键（如 `2:target_situation`）。
- 已提供 Alembic 迁移将旧键（如 `1:recent_pattern`、`4:top_reason`）迁到 PDF 命名，并移除 Stage0 `orientation_ack`。

## 摘要卡与 PDF 导出键

- `sessions.chat_summary_json.schema_version` 当前为 `4`。
- 主字段：`summary_reason`、`summary_trigger`、`summary_plan`、`summary_confidence`。
- 同时保留 `pdf_*` 字段（`pdf_recent_drinking_pattern` 等）用于论文表格直出。

## 轮次预算

- 目标区间：12–16 assistant turns（`study_target_assistant_turns_min/max`）。
- 服务端提供 `assistant_turns_so_far` 实时计数；到硬上限前会触发强制收敛并写 `turn_budget_exceeded` 审计。

## 材料版本（Methods 引用）

| 组件 | 字段来源 |
|------|----------|
| Prompt bundle | `sessions.prompt_bundle_version` |
| Strategy library version | `sessions.session_meta_json.strategy_library_version` + `audit_events.randomized` |
| LLM transport | `llm_calls.api_type` / `state.llm_api_type_label` |
| 摘要 schema | `chat_summary_json.schema_version=4` |
| 后测 schema | `survey_responses(schema_version=4, instrument=post)` |
| 前后端构建号 | `sessions.session_meta_json.frontend_build/backend_build` |
