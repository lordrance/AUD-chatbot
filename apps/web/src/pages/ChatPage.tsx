/**
 * 聊天页：多轮 POST chat/turn、消息 localStorage 缓存、快捷短语与安全提示条。
 */
import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import type { ChatMessage } from "../types";
import { ProgressBar } from "../components/ProgressBar";
import { HelpResourcesModal } from "../components/HelpResourcesModal";
import { loadSession, routeForStatus } from "../flow";
import { progressStepForPath } from "../flow";

const MSG_KEY = (id: string) => `safechat_aud_msgs_${id}`;
const PENDING_ASST_KEY = (id: string) => `safechat_aud_pending_asst_${id}`;

/** 非阻塞 UI 遥测（失败静默）。 */
function emitUiEvent(event_type: string, event_value?: string | null, turn_index?: number | null) {
  const s = loadSession();
  if (!s) return;
  void api
    .postUiEvent(s.sessionId, s.token, {
      event_type,
      event_value: event_value ?? undefined,
      turn_index: turn_index ?? undefined,
    })
    .catch(() => {});
}

const QUICK: Record<string, string[]> = {
  "0:preferred_name": ["Alex", "Sam"],
  "0:ready_to_start": ["Yes, this is a good time", "I'm free now"],
  "1:recent_drinking_pattern": ["About three or four times last week", "It varied"],
  "1:most_concerning_episode": ["Last weekend I drank more than I wanted", "After work on Friday"],
  "1:top_reason_to_cut_down": ["I want to drink less", "Mostly sleep and health"],
  "1:importance_0_10": ["7", "8"],
  "1:confidence_0_10": ["6", "7"],
  "2:target_situation": ["Work or social events", "When I'm home alone"],
  "2:where": ["At home", "At a bar"],
  "2:when": ["Friday evenings", "Late night"],
  "2:who_with": ["Coworkers", "I'm alone"],
  "2:emotion_or_state": ["Stressed", "Bored"],
  "2:immediate_trigger": ["Seeing the bottle", "End of the workday"],
  "3:selected_strategy": ["delay_first_drink", "alternate_with_water"],
  "3:if_then_plan": [
    "If it's Friday after work, I'll walk ten minutes before opening a drink.",
    "If there's a dinner out, I'll drink a glass of water first.",
  ],
  "3:likely_obstacle": ["Too tired", "Hard to say no"],
  "3:workaround": ["Set a phone reminder", "Leave early"],
  "3:final_confidence_0_10": ["8", "5"],
  "3:if_then_plan_revised": [
    "If it's Friday, I'll delay the first drink by five minutes only.",
    "If I want a drink, I'll pour water first and wait five minutes.",
  ],
  "3:final_confidence_0_10_after_shrink": ["8", "7"],
  "4:summary_reason": ["Sleep and health", "Family"],
  "4:summary_trigger": ["Friday stress", "Social events"],
  "4:summary_plan": ["If Friday, walk first then decide", "If dinner out, water first"],
  "4:summary_confidence": ["8", "7"],
  "4:optional_takeaway": ["none", "I'll try the smaller step"],
};

/** 将快捷语配置统一为字符串数组。 */
function normalizeQuick(val: string | string[]): string[] {
  return Array.isArray(val) ? val : [val];
}

/** 研究聊天主界面（含发送、跳过、资源弹窗）。 */
export function ChatPage() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [chatStage, setChatStage] = useState<number | null>(null);
  const [chatSection, setChatSection] = useState<number | null>(null);
  const [maxTurnsStage, setMaxTurnsStage] = useState<number | null>(null);
  const [turnsInStage, setTurnsInStage] = useState<number | null>(null);
  const [substate, setSubstate] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [done, setDone] = useState(false);
  const [safetyBanner, setSafetyBanner] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const idleTimerRef = useRef<number | null>(null);
  const editedSinceLastSendRef = useRef(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    emitUiEvent("refresh");
    const onVis = () => {
      emitUiEvent(document.hidden ? "page_blur" : "page_return");
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  useEffect(() => {
    if (busy) return;
    if (idleTimerRef.current) window.clearTimeout(idleTimerRef.current);
    idleTimerRef.current = window.setTimeout(() => {
      emitUiEvent("idle_timeout");
      idleTimerRef.current = null;
    }, 60_000);
    return () => {
      if (idleTimerRef.current) {
        window.clearTimeout(idleTimerRef.current);
        idleTimerRef.current = null;
      }
    };
  }, [busy, input, messages.length]);

  useEffect(() => {
    const s = loadSession();
    if (!s) {
      navigate("/");
      return;
    }
    let base: ChatMessage[] = [];
    try {
      const raw = localStorage.getItem(MSG_KEY(s.sessionId));
      if (raw) base = JSON.parse(raw) as ChatMessage[];
    } catch {
      /* ignore */
    }
    const pk = PENDING_ASST_KEY(s.sessionId);
    const pendingAsst = sessionStorage.getItem(pk);
    if (pendingAsst) {
      sessionStorage.removeItem(pk);
      base = [...base, { role: "assistant", text: pendingAsst }];
      localStorage.setItem(MSG_KEY(s.sessionId), JSON.stringify(base));
    }
    setMessages(base);

    api.getState(s.sessionId, s.token).then((st) => {
      if (st.status === "post_survey_pending") {
        navigate("/chat-summary");
        return;
      }
      if (st.status === "abandoned") {
        navigate("/safety-end?reason=emergency");
        return;
      }
      if (st.status === "stage1_feedback_pending") {
        navigate("/chat/stage1-feedback");
        return;
      }
      if (st.status !== "chat_ready" && st.status !== "chat_active") {
        navigate(routeForStatus(st.status));
        return;
      }
      setChatStage(st.chat_stage ?? st.current_stage ?? 0);
      setChatSection(st.chat_section_1_to_4 ?? null);
      setMaxTurnsStage(st.max_user_turns_current_stage ?? null);
      setTurnsInStage(st.user_turns_in_current_stage ?? null);
      setSubstate(st.current_substate);
      setSafetyBanner(!!st.safety_show_resources_prompt);
    });
  }, [navigate]);

  /** 将当前消息列表序列化到 localStorage。 */
  function persist(next: ChatMessage[]) {
    const s = loadSession();
    if (s) localStorage.setItem(MSG_KEY(s.sessionId), JSON.stringify(next));
  }

  /** 乐观更新用户消息后请求 API，合并助手回复并处理关闭/跳转。 */
  async function sendText(text: string, eventType: "send_message" | "skip_click" = "send_message") {
    const t = text.trim();
    if (!t) return;
    const s = loadSession();
    if (!s) return;
    setBusy(true);
    setErr(null);
    const userMsg: ChatMessage = { role: "user", text: t };
    const prev = messages;
    const next = [...prev, userMsg];
    const userTurnIndex = next.filter((m) => m.role === "user").length;
    emitUiEvent(eventType, undefined, userTurnIndex);
    editedSinceLastSendRef.current = false;
    setMessages(next);
    persist(next);
    setInput("");
    try {
      const res = await api.postChatTurn(s.sessionId, s.token, t, new Date().toISOString());
      const asst: ChatMessage = { role: "assistant", text: res.assistant_text };
      const withBot = [...next, asst];
      setMessages(withBot);
      persist(withBot);
      if (res.status_after === "abandoned") {
        setDone(true);
        navigate("/safety-end?reason=emergency");
        return;
      }
      const st = await api.getState(s.sessionId, s.token);
      setChatStage(st.chat_stage ?? st.current_stage ?? res.stage_after);
      setChatSection(st.chat_section_1_to_4 ?? null);
      setMaxTurnsStage(st.max_user_turns_current_stage ?? null);
      setTurnsInStage(st.user_turns_in_current_stage ?? null);
      setSubstate(st.current_substate);
      setSafetyBanner(!!st.safety_show_resources_prompt);
      if (res.safety_resources_suggested) {
        setHelpOpen(true);
      }
      if (res.stage1_feedback_required) {
        navigate("/chat/stage1-feedback");
        return;
      }
      if (res.chat_closed || st.post_survey_unlocked) {
        setDone(true);
        navigate("/chat-summary");
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Send failed");
      setMessages(prev);
      persist(prev);
    } finally {
      setBusy(false);
    }
  }

  const quick = substate && QUICK[substate] ? normalizeQuick(QUICK[substate]) : [];

  return (
    <>
      <ProgressBar
        step={progressStepForPath("/chat")}
        chatStage={chatStage}
        chatSectionOfFour={chatSection}
        userTurnsInStage={turnsInStage}
        maxUserTurnsStage={maxTurnsStage}
      />
      <section className="card chat-card">
        <h2>Research chat</h2>
        {safetyBanner && (
          <p className="notice" role="status">
            Suggestion: when you can, open Help & resources for support information. Unless the rules require ending the
            chat, you can usually keep replying.
          </p>
        )}
        <p className="muted small">
          Text only. Answer the questions you see; use quick phrases or type freely. This chat is{" "}
          <strong>not</strong> continuously monitored by staff.
          {done ? " The chat has ended; continuing to the next step…" : ""}
        </p>
        <div className="msg-list" role="log" aria-live="polite">
          {messages.length === 0 && (
            <p className="muted">
              Type your <strong>first</strong> reply below (for example, confirm you read the study information).
            </p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg msg-${m.role}`}>
              <span className="msg-label">{m.role === "user" ? "You" : "Assistant"}</span>
              <div className="msg-body">{m.text}</div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        {quick.length > 0 && (
          <div className="quick-row">
            <span className="muted small">Quick replies (optional):</span>
            {quick.map((q) => (
              <button
                key={q}
                type="button"
                className="chip"
                disabled={busy}
                onClick={() => {
                  emitUiEvent("quick_reply_click", q.length > 200 ? `${q.slice(0, 200)}…` : q);
                  setInput(q);
                }}
              >
                {q.length > 24 ? `${q.slice(0, 24)}…` : q}
              </button>
            ))}
          </div>
        )}
        {err && <p className="error">{err}</p>}
        <div className="chat-input-row">
          <textarea
            value={input}
            onChange={(e) => {
              const nextInput = e.target.value;
              setInput(nextInput);
              if (!editedSinceLastSendRef.current && nextInput.trim().length > 0) {
                emitUiEvent("edit_before_send");
                editedSinceLastSendRef.current = true;
              }
            }}
            onPaste={() => emitUiEvent("paste_detected")}
            onFocus={() => emitUiEvent("focus_input")}
            onBlur={() => emitUiEvent("page_blur")}
            placeholder="Type your reply…"
            rows={3}
            disabled={busy}
            maxLength={4000}
          />
          <div className="chat-actions">
            <button type="button" className="btn" disabled={busy} onClick={() => sendText(input, "send_message")}>
              Send
            </button>
            <button
              type="button"
              className="btn secondary"
              disabled={busy}
              onClick={() => sendText("(skip)", "skip_click")}
              title="Sends a placeholder reply; still counts as one user turn"
            >
              Skip this turn
            </button>
            <button type="button" className="btn tertiary" onClick={() => setHelpOpen(true)}>
              Help & resources
            </button>
          </div>
        </div>
      </section>
      <HelpResourcesModal open={helpOpen} onClose={() => setHelpOpen(false)} />
    </>
  );
}
