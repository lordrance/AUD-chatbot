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
}

/** 浏览器中展示的一条聊天消息。 */
export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}
