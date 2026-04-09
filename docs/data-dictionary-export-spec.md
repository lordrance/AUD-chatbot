# 分析用数据字典与导出规格（SafeChat-AUD v1）

本文档描述**试点导出/分析**时的核心字段含义与表关系。实现上可直接从 PostgreSQL 按表 JOIN `session_id`（UUID）汇总。

---

## A. 主体会话与流程状态（`sessions`）

| 字段 | 类型（概念） | 说明 |
|------|----------------|------|
| `id` | UUID | 会话主键；全表外键锚点 |
| `session_token` | 字符串 | 被试 API 认证用（**敏感**；导出分析常脱敏或哈希） |
| `status` | 枚举字符串 | `consent_pending` … `completed` / `ineligible` / `abandoned` 等 |
| `arm` | 字符串 \| null | 三臂：`neutral_professional` / `supportive_practical` / `warm_empathic`；历史数据可能为 `empathic` / `neutral` |
| `fsm_stage` | int | 聊天 FSM 当前/结束阶段（0–4，结束后进入后测时可能停在末段） |
| `dropout_stage` | 字符串 \| null | 中止编码，如 `safety_pre_chat`、`safety_emergency_in_chat` |
| `prompt_bundle_version` | 字符串 \| null | 冻结的提示词包引用（如 `safechat-aud@0.2.1`），与 **prompt_version** 日志一致 |
| `consent_document_version` | 字符串 \| null | 提交的同意书版本号 |
| `chat_started_at` / `chat_completed_at` | timestamptz \| null | 聊天起止 |
| `chat_exchange_index` | int | 已分配的对话轮次序号（每用户消息通常 +1） |
| `chat_last_turn_index` | int | 最后一条 `chat_turns.turn_index` 相关计数 |
| `chat_user_turns_in_stage` | int | 当前阶段内用户轮次计数 |
| `slot_json` | JSONB | FSM 槽位原文；**转写/对话结构化输入**（见 B 节） |
| `rolling_summary` | text | 服务端滚动摘要串（研究用轨迹压缩） |
| **`chat_summary_json`** | JSONB \| null | **摘要卡**（聊天结束进入后测等时点写入）；结构见下文 **D** |
| **`session_meta_json`** | JSONB | 会话级版本与观测字段：`model_id`、`api_type`、`store_flag`、`global/style/stage_prompt_version`、`strategy_library_version`、`frontend_build`、`backend_build` |
| `safety_max_severity` | int | 0–3 |
| `safety_last_routing_action` | 字符串 \| null | 如 `CONTINUE`、`SHOW_RESOURCES_AND_END_CHAT`、`EMERGENCY_STOP` |
| `safety_flags` | JSONB 数组 | 各次扫描事件条目（含 `phase`、`codes`、`severity` 等） |
| `safety_policy_chat_ended` | bool | 是否因安全策略结束聊天 |
| `ineligible_reasons` | JSONB \| null | 不合格时编码与总分等 |
| `created_at` / `updated_at` / `last_activity_at` | timestamptz | 审计与活动时间 |

**「阶段到达」**：以 `status`、`chat_completed_at`、`fsm_stage` 及 `audit_events`（如 `chat_completed`、`chat_completed_safety`）共同判定。

**「每阶段用户轮次」**：由 `chat_turns` 按 `stage` + `role='user'` 聚合 `count(*)`（见 B）。

---

## B. 对话转写与过程元数据（`chat_turns`）— 与随访/联系人分离

每条为一轮用户或助手消息。**导出时注意**：`text` / `user_text` / `assistant_text` 为**转写内容**，与 **E 节随访** 及联系方式元数据分开存储与授权。

| 字段 | 说明 |
|------|------|
| `session_id` | FK → `sessions.id` |
| `exchange_index` | 与一轮问答对齐 |
| `turn_index` | 单调序号 |
| `role` | `user` / `assistant` |
| `stage` | 该轮所在 FSM 阶段 0–4 |
| `arm` | 冗余实验臂 |
| `text` | 展示用正文 |
| `user_text` / `assistant_text` | 分角色副本 |
| `latency_ms` | 助手轮次从收到用户到就绪的延迟（毫秒）；用户轮常为 null |
| `server_received_at` / `response_ready_at` | timestamptz |
| **`stub_meta`** | JSONB：含 **`prompt_version`**、本回合 **`safety_flags`**（代码列表）、**`safety_routing_action`**、**`safety_severity_this_turn`**、`slot_filled`、`stage_at_request`、`fsm_stage_after`、LLM 尝试/错误/`model` 相关键；LLM 路径另含 **`dialogue_acts`**、**`next_action`**、**`model_reported_stage`**、**`llm_risk_block`**、**`extracted_slots`**、**`selected_strategy_ids`**、**`llm_api_type`**（如 `chat_completions`）等（无 key 时多为 stub） |

**聚合示例（思路）**：`GROUP BY session_id, stage WHERE role='user'` → 每阶段用户发言条数。

---

## C. LLM 调用日志（`llm_calls`）— prompt / model / 延迟 / tokens

无 API Key 或非 LLM 路径时可能**无记录**或 `success=false`。

| 字段 | 说明 |
|------|------|
| `session_id` | FK |
| `exchange_index` | 与 `chat_turns` 对齐 |
| **`prompt_version`** | 提示词包引用 |
| **`model_version`** | 模型标识字符串 |
| `latency_ms` | 调用耗时 |
| `prompt_tokens` / `completion_tokens` / `total_tokens` | 可空 |
| `api_type` | `responses` / `chat_completions_fallback` 等 |
| `previous_response_id` | Responses API 上下文链路（可空） |
| `success` / `fallback_used` / `fallback_reason` / `error_message` | 成功与否与回退 |
| `retry_count` / `finish_reason` / `refusal_flag` | 调用重试与终止信息 |
| `normalized_output` / `raw_content` | 结构化/原始输出（成功时 `normalized_output` 为 **`LlmTurnStructuredOutput`** 的 JSON，含 `dialogue_acts`、`risk`、`next_action` 等；体积可能大） |

---

## D. 结构化摘要卡（`sessions.chat_summary_json`）

由 `app/services/chat_summary.py` 生成，`schema_version` 当前为 **`"4"`**（与常量 `CHAT_SUMMARY_SCHEMA_VERSION` 一致）。

| JSON 键 | 说明 |
|---------|------|
| `schema_version` | `"4"` |
| `preferred_name`, `summary_reason`, `summary_trigger`, `summary_plan` | Stage 0–4 槽位聚合 |
| `summary_confidence`, `optional_takeaway` | Stage 4 |
| `selected_strategy`, `trigger_context`, `micro_plan_if_then` | Stage 2–3 |
| `change_readiness_baseline_1_10`, `importance_to_reduce_baseline_0_10` | 来自基线问卷 |
| `confidence_summary` | 可读摘要（基线 + 各阶段信心）；可空 |
| **`pdf_*`** | 与 answer2 论文表对齐的别名（如 `pdf_recent_drinking_pattern`, `pdf_if_then_plan` 等）；见 `docs/slot-schema-and-stages.md` |
| **Legacy** | `top_reason_to_cut_down`, `top_trigger_high_risk_situation`, `support_focus` 等仍写入以便旧脚本 |

**来源**：以 `slot_json` + 基线为主；**非**全文 LLM 摘要。

---

## E. 问卷原始答案（`survey_responses`）

按 `instrument` + `schema_version` 区分。**答案体**在 **`answers`** JSONB。

| instrument | schema_version（v1 冻结） | 说明 |
|------------|---------------------------|------|
| `consent` | `1` | 含 `consent_accepted`、`consent_document_version` |
| `eligibility` | `1` | AUDIT-C 等；含服务端衍生 `computed_*`、`passed` |
| `baseline` | `1` | `typical_drinks_last_week`、`readiness_to_change_1_10`、`primary_concern_short` 等 |
| `post` | **`4`** | 后测；字段与 **`PostSurveySubmit`** / `SURVEY_SCHEMA_POST` 一致，见下 **F** |

---

## F. 后测字段（`instrument=post`, `schema_version=4`）

写入 `answers` 的键（与 API `PostSurveySubmit` 对齐）：

| 键 | 类型 | 说明 |
|----|------|------|
| `wai_tech_sf_item_01` … `wai_tech_sf_item_12` | int 1–7 | WAI-TECH-SF |
| `trust_1_5` | int 1–5 | 信任 |
| `helpfulness_1_5` | int 1–5 | 有帮助 |
| `disclosure_comfort_1_5` | int 1–5 | 披露舒适度 |
| `change_intention_1_5` | int 1–5 | 改变意向 |
| `manipulation_felt_warm_1_5` | int 1–5 | 操纵检验（温暖） |
| `manipulation_felt_professional_1_5` | int 1–5 | 操纵检验（专业克制） |
| `manipulation_felt_practical_actionable_1_5` | int 1–5 | 操纵检验（**B 臂**：务实可执行） |
| `manipulation_understood_feelings_1_5` | int 1–5 | 操纵检验 |
| `manipulation_felt_repetitive_1_5` | int 1–5 | 同上（越高越重复/脚本感） |
| `manipulation_felt_personal_tailored_1_5` | int 1–5 | 同上 |
| `open_most_helpful` | 字符串 | 开放题 |
| `open_unnatural_or_uncomfortable` | 字符串 | 开放题 |

---

## G. 随访与联系数据（`session_followups`）— **与转写分离**

**存储合规提示**：`contact_json` 可能含邮箱/电话；`response_json` 为随访自陈。**访问控制**应与对话转写 (`chat_turns.text`) 区分（不同角色、脱敏策略）。

| 字段 | 说明 |
|------|------|
| `session_id` | 唯一 FK → `sessions.id` |
| `followup_token` | 公开随访链接令牌（**敏感**，导出需限制） |
| **`contact_json`** | JSON：`email`、`phone` 等（可空键） |
| `opt_in_at` | timestamptz |
| **`response_json`** | 提交后写入；键见 **`FollowUpSurveySubmit`** |
| `submitted_at` | timestamptz \| null |
| **`response_schema_version`** | v1 冻结为 **`"1"`**（`SURVEY_SCHEMA_FOLLOWUP_7D`） |

### `response_json` 键（schema 1）

| 键 | 说明 |
|----|------|
| `drinking_days_last_7` | 0–7 |
| `heavy_drinking_days_last_7` | 0–7，≤ 上一项 |
| `used_plan` | `yes` / `no` / `somewhat` |
| `intention_confidence_reduce_1_10` | 1–10 |
| `willing_to_use_again_1_5` | 1–5 |

---

## H. 阶段状态快照（`stage_state_events`）

| 字段 | 说明 |
|------|------|
| `session_id` | FK |
| `turn_index` | 对应 chat_turn 序号 |
| `current_stage` | 快照时阶段 |
| `slots_json` | 当时槽位全量 |
| `stage_complete` | 当前阶段是否已满 |
| `reason_for_transition` | `slot_update` / `stage_complete` / `turn_budget_force_close` 等 |
| `importance_score` / `confidence_score` | 过程评分快照 |
| `selected_strategy_ids` | 该轮策略 id 数组 |
| `if_then_plan` | 当前 if–then 文本 |
| `rolling_summary` | 截断摘要 |

---

## I. 过程审计（`audit_events`）

| 字段 | 说明 |
|------|------|
| `event_type` | 如 `session_created`、`randomized`、`chat_completed`、`stage_transition`、`turn_budget_exceeded`、`safety_routing_transition`、`ui_event`、`style_fidelity_tagged`、`followup_opt_in` |
| `payload` | JSONB；当审计行 `event_type` 为 **`ui_event`** 时，payload 内另有字段 **`event_type`**（交互子类型，如 `user_send`）、`event_value`、`fsm_stage`、`received_at` 等；安全相关事件常含 `routing_action`、`severity`、`phase` 等 |

**前端 UI 事件（`event_type=ui_event`）**：典型子类型包括 `focus_input`、`send_message`、`quick_reply_click`、`skip_turn`、`page_blur`、`page_return`、`idle_timeout`、`survey_start`、`survey_submit`（见 `apps/web`）。

---

## J. 导出边界小结

| 类别 | 主要表 / 字段 |
|------|----------------|
| **转写 / 槽位原文** | `chat_turns`、`sessions.slot_json`、`rolling_summary` |
| **结构化摘要（非全文）** | `sessions.chat_summary_json` |
| **主研究问卷** | `survey_responses`（consent / eligibility / baseline / post） |
| **随访自陈 + 联系方式** | `session_followups`（**勿与转写混表不加控**） |
| **模型与提示词版本、延迟** | `llm_calls`、`chat_turns.stub_meta` |
| **安全与路由** | `sessions.safety_*`、`stub_meta`、`audit_events` |

本文档与 **`docs/v1-pilot-freeze.md`** 中的版本号一并冻结；字段增改应 bump schema 或文档版本。
