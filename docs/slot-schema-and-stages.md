# Slot schema 与聊天阶段（对齐 answer2.pdf「研究仪器」设计）

本文档把 **槽位（slot）**、**阶段（stage）**、**操纵条件（三臂）** 与 **YAML 提示词文件** 的对应关系写清楚，便于冻结与伦理/方法学材料引用。权威实现见 `apps/api/app/services/chat_fsm.py` 中的 `REQUIRED_SLOTS_BY_STAGE`。

## 实验条件（单因素三水平，可配置为两臂）

- **内部 `arm` 值（随机分组）**：`neutral_professional`（A）、`supportive_practical`（B）、`warm_empathic`（C）。历史会话可能仍为 `empathic` / `neutral`（由 `arm_styles` 归一）。
- **风格块**：`prompts/neutral.yaml`、`prompts/supportive_practical.yaml`、`prompts/warm.yaml` + 各 `stage_*` 内同名键；**global** 与 **stage 骨架**三组一致，差异仅在风格 YAML。
- **随机化模式**：`RANDOMIZATION_MODE`（`three_arm` / `two_arm_ac`）见 `apps/api/app/config.py`；审计事件 `randomized` 的 payload 含 `randomization_mode`、`strategy_library_version` 等。

## 阶段总览

| Stage | 主题 | 提示词文件 | 必须填满的槽位（按顺序） |
|-------|------|------------|---------------------------|
| 0 | 说明与就绪 | `stage_0_onboarding.yaml` | `preferred_name`, `orientation_ack`, `ready_to_start` |
| 1 | 近期饮酒与动机 + 0–10 | `stage_1_assess.yaml` | `recent_pattern`, `most_concerning_episode`, `reason_to_cut_down`, `importance_rating_0_10`, `confidence_rating_0_10` |
| 2 | 高风险情境细化 | `stage_2_triggers.yaml` | `target_high_risk_situation`, `people`, `place`, `time`, `emotion_or_internal_state`, `cue_or_trigger` |
| 3 | 策略与 if–then 计划 | `stage_3_plan.yaml` | `selected_target_situation`, `selected_strategy`, `if_then_plan`, `obstacle`, `workaround`, `final_confidence_0_10`；若 `final_confidence_0_10` 为有效整数且 **&lt;7**，服务端再要求 `if_then_plan_revised`、`final_confidence_0_10_after_shrink` |
| 4 | 摘要卡字段 | `stage_4_close.yaml` | `top_reason`, `top_trigger`, `chosen_plan`, `closing_confidence_0_10`, `optional_takeaway` |

### Stage 3 策略库（8 条，每轮最多呈现 2 条）

- 权威列表：`prompts/strategies.json`（含 `version`，如 `0.3`）。
- 服务端 `strategy_library.pick_offered_strategy_ids` 注入上下文；模型 `selected_strategy_ids` 须来自库内 id。

### Stage 4 收尾句

- 各风格在 `stage_4_close.yaml` 的 `sign_off`（或由 stub 拼接），与操纵条件 A/B/C 一致。

## 存储格式

- 服务端在 `sessions.slot_json` 中以 **`"{stage}:{slot_name}"`** 为键保存用户已提供内容（见 `qualified_slot_key`）。
- **何时进入下一阶段**：当前 stage 内所有 required slots 非空后，由 FSM 将 `fsm_stage` 递增；**不由模型决定**是否跳阶段。阶段变化写入审计 `stage_transition`。

## 与 PDF / 论文表的键名对照（导出）

内部槽位键不变；`sessions.chat_summary_json` 在 `schema_version` **3** 下额外包含 `pdf_*` 字段，与 answer2 命名对齐（见 `apps/api/app/services/chat_summary.py`）。

| 内部槽位（阶段） | PDF / 导出键（`chat_summary_json`） |
|------------------|-------------------------------------|
| `1:recent_pattern` | `pdf_recent_drinking_pattern` |
| `1:most_concerning_episode` | `pdf_most_concerning_episode` |
| `1:reason_to_cut_down` | `pdf_top_reason_to_cut_down` |
| `2:target_high_risk_situation` | `pdf_target_situation` |
| `2:place` / `time` / `people` | `pdf_where` / `pdf_when` / `pdf_who_with` |
| `2:emotion_or_internal_state` | `pdf_emotion_or_state` |
| `2:cue_or_trigger` | `pdf_immediate_trigger` |
| `3:selected_strategy` | `pdf_selected_strategy` |
| `3:if_then_plan`（或 revised） | `pdf_if_then_plan` |
| `3:obstacle` / `3:workaround` | `pdf_likely_obstacle` / `pdf_workaround` |

## 与「任务 1」的对应关系

- **Stage 1 / 2 怎么问**：见 `prompts/stage_1_assess.yaml`、`prompts/stage_2_triggers.yaml`（及 `bundles/` 下各版本快照）。
- **收集哪些信息**：上表槽位即最小必要信息集；当前实现仍为**大体每槽一轮用户消息**（基础路径约 25 条用户消息）。协议目标 **12–16 个 bot turns** 与方法论文中应对照 `GET /state` 的 `study_target_assistant_turns_min` / `max` 与 **`assistant_turns_so_far`**（已落库助手消息计数）；若需严格压预算，需另行调整 FSM/合并轮次（产品确认后）。

## 材料版本化（Methods 引用）

| 组件 | 版本来源 |
|------|-----------|
| 提示词包 | `sessions.prompt_bundle_version`（随机化时冻结）；manifest 见 `prompts/manifest.yaml` |
| 策略库 | `strategies.json` 内 `version`；审计 `randomized.strategy_library_version` |
| 摘要卡 schema | `chat_summary_json.schema_version`（当前 **3**） |
| 后测问卷 schema | `survey_responses.schema_version`，`instrument=post` 当前为 **4**（见 `SURVEY_SCHEMA_POST`） |
| 前端构建 | 建议在部署时注入环境变量并在审计或导出中记录（待运维管线） |
