# Slot schema 与聊天阶段（对齐 answer 文档「研究仪器」设计）

本文档把 **槽位（slot）**、**阶段（stage）** 与 **YAML 提示词文件** 的对应关系写清楚，便于冻结与伦理/方法学材料引用。权威实现见 `apps/api/app/services/chat_fsm.py` 中的 `REQUIRED_SLOTS_BY_STAGE`。

## 阶段总览

| Stage | 主题 | 提示词文件 | 必须填满的槽位（按顺序） |
|-------|------|------------|---------------------------|
| 0 | 说明与就绪 | `stage_0_onboarding.yaml` | `preferred_name`, `orientation_ack`, `ready_to_start` |
| 1 | 近期饮酒与动机 + 0–10 | `stage_1_assess.yaml` | `recent_pattern`, `most_concerning_episode`, `reason_to_cut_down`, `importance_rating_0_10`, `confidence_rating_0_10` |
| 2 | 高风险情境细化 | `stage_2_triggers.yaml` | `target_high_risk_situation`, `people`, `place`, `time`, `emotion_or_internal_state`, `cue_or_trigger` |
| 3 | 策略与 if–then 计划 | `stage_3_plan.yaml` | `selected_target_situation`, `selected_strategy`, `if_then_plan`, `obstacle`, `workaround`, `final_confidence_0_10`；若 `final_confidence_0_10` 为有效整数且 **&lt;7**，服务端再要求 `if_then_plan_revised`、`final_confidence_0_10_after_shrink` |
| 4 | 摘要卡字段 | `stage_4_close.yaml` | `top_reason`, `top_trigger`, `chosen_plan`, `closing_confidence_0_10`, `optional_takeaway` |

## 存储格式

- 服务端在 `sessions.slot_json` 中以 **`"{stage}:{slot_name}"`** 为键保存用户已提供内容（见 `qualified_slot_key`）。
- **何时进入下一阶段**：当前 stage 内所有 required slots 非空后，由 FSM 将 `fsm_stage` 递增；**不由模型决定**是否跳阶段。

## 与「任务 1」的对应关系

- **Stage 1 / 2 怎么问**：见 `prompts/stage_1_assess.yaml`、`prompts/stage_2_triggers.yaml`（及 `bundles/` 下各版本快照）。
- **收集哪些信息**：上表槽位即最小必要信息集；**基础路径共 25 条用户消息**（每槽一轮）。Stage 3 若首次信心 &lt;7，再 **+2** 轮。`eval/run_batch.py` 在 persona 的 `user_turns` 条数不符时可回退到内置默认序列。

## 与策略库的关系

- Stage 3 的 `stage_hint` 要求模型可引用 **`prompts/strategies.json`** 中的 `strategy_id`；两臂共用同一策略库，操纵变量仅在 **warm / neutral 风格**（见 `warm.yaml` / `neutral.yaml`）。
