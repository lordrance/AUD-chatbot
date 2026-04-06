/**
 * 前端流程工具：localStorage 中的会话 id/token，以及按服务端 status 与路径计算路由、进度条步数。
 */

/** 将服务端会话状态映射为参与者应进入的前端路径。 */
export function routeForStatus(status: string): string {
  switch (status) {
    case "consent_pending":
      return "/consent";
    case "eligibility_pending":
      return "/eligibility";
    case "baseline_pending":
      return "/baseline";
    case "pending_randomization":
      return "/randomize";
    case "chat_ready":
    case "chat_active":
      return "/chat";
    case "post_survey_pending":
      return "/chat-summary";
    case "completed":
      return "/thank-you";
    case "ineligible":
      return "/ineligible";
    case "abandoned":
      return "/safety-end";
    default:
      return "/";
  }
}

/** 根据当前 pathname 返回进度条步骤索引（含摘要卡与后测）。 */
export function progressStepForPath(pathname: string): number {
  if (pathname === "/" || pathname === "/orient") return 0;
  if (pathname === "/consent") return 1;
  if (pathname === "/eligibility") return 2;
  if (pathname === "/baseline") return 3;
  if (pathname === "/randomize") return 4;
  if (pathname === "/chat") return 5;
  if (pathname === "/chat-summary") return 6;
  if (pathname === "/post-survey") return 7;
  if (pathname === "/thank-you") return 8;
  if (pathname === "/ineligible") return 0;
  return 0;
}

export const STORAGE_ID = "safechat_aud_session_id";
export const STORAGE_TOKEN = "safechat_aud_session_token";

/** 清除本地保存的会话标识（不清理聊天消息缓存，由业务页处理）。 */
export function clearSessionStorage(): void {
  localStorage.removeItem(STORAGE_ID);
  localStorage.removeItem(STORAGE_TOKEN);
}

/** 写入会话 id 与 Bearer token。 */
export function saveSession(sessionId: string, token: string): void {
  localStorage.setItem(STORAGE_ID, sessionId);
  localStorage.setItem(STORAGE_TOKEN, token);
}

/** 读取已保存会话；缺一则返回 null。 */
export function loadSession(): { sessionId: string; token: string } | null {
  const sessionId = localStorage.getItem(STORAGE_ID);
  const token = localStorage.getItem(STORAGE_TOKEN);
  if (!sessionId || !token) return null;
  return { sessionId, token };
}
