# Slot schema 与聊天阶段（对齐 answer 文档「研究仪器」设计）

本文档把 **槽位（slot）**、**阶段（stage）** 与 **YAML 提示词文件** 的对应关系写清楚，便于冻结与伦理/方法学材料引用。权威实现见 `apps/api/app/services/chat_fsm.py` 中的 `REQUIRED_SLOTS_BY_STAGE`。

## 阶段总览

| Stage | 主题 | 提示词文件 | 必须填满的槽位（按顺序） |
|-------|------|------------|---------------------------|
| 0 | 说明与就绪 | `stage_0_onboarding.yaml` | `orientation_ack`, `time_ok` |
| 1 | 近期饮酒与动机 | `stage_1_assess.yaml` | `recent_drinking`, `reduce_motivation` |
| 2 | 触发情境 | `stage_2_triggers.yaml` | `main_trigger`, `trigger_context` |
| 3 | 支持焦点与微计划 | `stage_3_plan.yaml` | `support_focus`, `micro_plan_step` |
| 4 | 收尾确认 | `stage_4_close.yaml` | `closing_ack` |

## 存储格式

- 服务端在 `sessions.slot_json` 中以 **`"{stage}:{slot_name}"`** 为键保存用户已提供内容（见 `qualified_slot_key`）。
- **何时进入下一阶段**：当前 stage 内所有 required slots 非空后，由 FSM 将 `fsm_stage` 递增；**不由模型决定**是否跳阶段。

## 与「任务 1」的对应关系

- **Stage 1 / 2 怎么问**：见 `prompts/stage_1_assess.yaml`、`prompts/stage_2_triggers.yaml`（及 `bundles/` 下各版本快照）。
- **收集哪些信息**：上表槽位即最小必要信息集；与 `eval/personas.yaml` 中每条 persona 的 9 轮 `user_turns` 顺序一致（阶段 0 两槽 + 阶段 1–4 各两槽，阶段 4 仅一槽，共 9 条用户消息）。

## 与策略库的关系

- Stage 3 的 `stage_hint` 要求模型可引用 **`prompts/strategies.json`** 中的 `strategy_id`；两臂共用同一策略库，操纵变量仅在 **warm / neutral 风格**（见 `warm.yaml` / `neutral.yaml`）。
