/**
 * 浏览器端 REST 封装：Bearer 会话鉴权、统一 HttpError、与 /api/v1 对齐。
 */
import type { SessionState } from "./types";

const B = "/api/v1";

/** 带 HTTP 状态与响应体的可抛出错误，便于页面区分 403 等场景。 */
export class HttpError extends Error {
  constructor(
    message: string,
    public status: number,
    public body: unknown,
  ) {
    super(message);
    this.name = "HttpError";
  }
}

/** 构造带 Authorization 与 JSON Content-Type 的请求头。 */
function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

/** GET 同意书 Markdown 与版本号（无需登录）。 */
export async function getConsentDocument(): Promise<{
  consent_document_version: string;
  format: string;
  body: string;
}> {
  const r = await fetch(`${B}/consent-document`);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new HttpError(typeof body === "string" ? body : JSON.stringify(body), r.status, body);
  return body as { consent_document_version: string; format: string; body: string };
}

/** POST 创建新会话，返回 session_id 与 session_token。 */
export async function createSession(): Promise<{ session_id: string; session_token: string }> {
  const r = await fetch(`${B}/sessions`, { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/** GET 当前会话聚合状态（阶段、槽位、安全提示等）。 */
export async function getState(sessionId: string, token: string): Promise<SessionState> {
  const r = await fetch(`${B}/sessions/${sessionId}/state`, { headers: authHeaders(token) });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new HttpError(typeof body === "string" ? body : JSON.stringify(body), r.status, body);
  return body as SessionState;
}

/** POST 提交知情同意。 */
export async function postConsent(
  sessionId: string,
  token: string,
  body: { consent_accepted: true; consent_document_version: string },
) {
  const r = await fetch(`${B}/sessions/${sessionId}/consent`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/** POST 资格筛查；失败时响应体含 reasons / message。 */
export async function postEligibility(sessionId: string, token: string, body: Record<string, unknown>) {
  const r = await fetch(`${B}/sessions/${sessionId}/eligibility`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(typeof data === "object" ? JSON.stringify(data) : String(data));
  return data as { ok: boolean; status?: string; passed?: boolean; message?: string; reasons?: string[] };
}

/** POST 基线问卷。 */
export async function postBaseline(sessionId: string, token: string, body: Record<string, unknown>) {
  const r = await fetch(`${B}/sessions/${sessionId}/surveys/baseline`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/** POST 随机分组；安全拦截时可能 403 且 body 为对象。 */
export async function postRandomize(sessionId: string, token: string) {
  const r = await fetch(`${B}/sessions/${sessionId}/randomize`, {
    method: "POST",
    headers: authHeaders(token),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new HttpError(typeof body === "string" ? body : JSON.stringify(body), r.status, body);
  return body as { ok?: boolean; status: string; arm: string; already_assigned?: boolean };
}

/** POST 发送一轮聊天用户文本，返回助手回复与是否关闭聊天等。 */
export async function postChatTurn(sessionId: string, token: string, text: string) {
  const r = await fetch(`${B}/sessions/${sessionId}/chat/turn`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ text }),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new HttpError(typeof body === "string" ? body : JSON.stringify(body), r.status, body);
  return body as {
    assistant_text: string;
    stub: boolean;
    stage_after: number;
    chat_closed: boolean;
    status_after: string;
    stage1_feedback_required?: boolean;
    safety_severity_this_turn?: number;
    safety_routing_action?: string;
    safety_resources_suggested?: boolean;
  };
}

/** POST Stage1 反馈确认后继续聊天（下发 Stage2 首问）。 */
export async function postStage1FeedbackContinue(sessionId: string, token: string) {
  const r = await fetch(`${B}/sessions/${sessionId}/chat/stage1-feedback/continue`, {
    method: "POST",
    headers: authHeaders(token),
    body: "{}",
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new HttpError(typeof body === "string" ? body : JSON.stringify(body), r.status, body);
  return body as {
    ok: true;
    assistant_text: string;
    stub: boolean;
    status_after: string;
    exchange_index: number;
    prompt_version?: string | null;
  };
}

/** POST 登记 7 天随访并生成公开链接路径。 */
export async function postFollowUpOptIn(
  sessionId: string,
  token: string,
  body: { opted_in: true; contact_email?: string; contact_phone?: string },
) {
  const r = await fetch(`${B}/sessions/${sessionId}/followup/opt-in`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
  const resBody = await r.json().catch(() => ({}));
  if (!r.ok) throw new HttpError(typeof resBody === "string" ? resBody : JSON.stringify(resBody), r.status, resBody);
  return resBody as { ok: true; followup_token: string; followup_public_path: string };
}

/** GET 随访 token 是否可填、是否已提交。 */
export async function getFollowUpState(token: string) {
  const r = await fetch(`${B}/follow-up/${encodeURIComponent(token)}`);
  const resBody = await r.json().catch(() => ({}));
  if (!r.ok) throw new HttpError(typeof resBody === "string" ? resBody : JSON.stringify(resBody), r.status, resBody);
  return resBody as { can_submit: boolean; already_submitted: boolean; schema_version: string };
}

/** POST 提交公开随访问卷（仅 token，无 Bearer）。 */
export async function postFollowUpSurvey(
  token: string,
  body: {
    drinking_days_last_7: number;
    heavy_drinking_days_last_7: number;
    used_plan: "yes" | "no" | "somewhat";
    intention_confidence_reduce_1_10: number;
    willing_to_use_again_1_5: number;
  },
) {
  const r = await fetch(`${B}/follow-up/${encodeURIComponent(token)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const resBody = await r.json().catch(() => ({}));
  if (!r.ok) throw new HttpError(typeof resBody === "string" ? resBody : JSON.stringify(resBody), r.status, resBody);
  return resBody as { ok: true };
}

/** POST 研究 UI 事件（写入服务端审计队列）。 */
export async function postUiEvent(
  sessionId: string,
  token: string,
  body: { event_type: string; event_value?: string | null; turn_index?: number | null },
) {
  const r = await fetch(`${B}/sessions/${sessionId}/instrument/ui-event`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
  const resBody = await r.json().catch(() => ({}));
  if (!r.ok) throw new HttpError(typeof resBody === "string" ? resBody : JSON.stringify(resBody), r.status, resBody);
  return resBody as { ok: true };
}

/** POST 后测问卷。 */
export async function postPostSurvey(sessionId: string, token: string, body: Record<string, unknown>) {
  const r = await fetch(`${B}/sessions/${sessionId}/surveys/post`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
