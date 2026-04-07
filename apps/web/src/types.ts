/**
 * 与后端 GET /sessions/{id}/state 及聊天 UI 相关的 TypeScript 类型。
 */

/** 会话聚合状态（与 OpenAPI 字段一致，部分安全字段可选）。 */
export interface SessionState {
  session_id: string;
  status: string;
  arm: string | null;
  fsm_stage: number;
  chat_stage: number | null;
  current_stage: number | null;
  chat_enabled: boolean;
  chat_open: boolean;
  chat_completed: boolean;
  post_survey_unlocked: boolean;
  next_step: string;
  expected_consent_version: string;
  ineligible_reason: string | null;
  user_turns_in_current_stage: number | null;
  current_substate: string | null;
  slot_json: Record<string, unknown> | null;
  rolling_summary: string | null;
  prompt_version: string | null;
  dropout_stage?: string | null;
  safety_max_severity?: number;
  safety_last_routing_action?: string | null;
  safety_show_resources_prompt?: boolean;
  safety_chat_permitted?: boolean;
  /** 服务端 chat_summary_json 的解析结果 */
  chat_summary?: Record<string, unknown> | null;
  /** 聊天四段进度 1–4（Stage3–4 合并为第 4 段） */
  chat_section_1_to_4?: number | null;
  max_user_turns_current_stage?: number | null;
  stage1_feedback_card?: Record<string, unknown> | null;
  study_target_assistant_turns_min?: number | null;
  study_target_assistant_turns_max?: number | null;
  llm_api_type_label?: string | null;
  assistant_turns_so_far?: number | null;
}

/** 浏览器中展示的一条聊天消息。 */
export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}
