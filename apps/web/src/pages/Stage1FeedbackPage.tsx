/**
 * Stage 1 结束反馈卡：展示基线饮酒量与 Stage1 槽位摘要，确认后继续 Stage2。
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import { ProgressBar } from "../components/ProgressBar";
import { loadSession, routeForStatus, progressStepForPath } from "../flow";

const PENDING_ASST_KEY = (id: string) => `safechat_aud_pending_asst_${id}`;

/** Stage1 反馈与继续（写入 sessionStorage 供 Chat 页拼接首条 Stage2 助手消息）。 */
export function Stage1FeedbackPage() {
  const navigate = useNavigate();
  const [card, setCard] = useState<Record<string, unknown> | null | undefined>(undefined);
  const [chatSection, setChatSection] = useState<number | null>(2);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const s = loadSession();
    if (!s) {
      navigate("/");
      return;
    }
    api.getState(s.sessionId, s.token).then((st) => {
      if (st.status === "completed") navigate("/thank-you");
      else if (st.status !== "stage1_feedback_pending") navigate(routeForStatus(st.status));
      else {
        setChatSection(st.chat_section_1_to_4 ?? 2);
        setCard((st.stage1_feedback_card as Record<string, unknown>) ?? null);
      }
    });
  }, [navigate]);

  async function onContinue() {
    const s = loadSession();
    if (!s) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await api.postStage1FeedbackContinue(s.sessionId, s.token);
      sessionStorage.setItem(PENDING_ASST_KEY(s.sessionId), res.assistant_text);
      navigate("/chat");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Continue failed");
    } finally {
      setBusy(false);
    }
  }

  const slots = card && typeof card.stage1_slots === "object" && card.stage1_slots !== null
    ? (card.stage1_slots as Record<string, unknown>)
    : null;
  const drinks = card?.typical_drinks_last_week_baseline;

  return (
    <>
      <ProgressBar
        step={progressStepForPath("/chat/stage1-feedback")}
        chatSectionOfFour={chatSection}
        userTurnsInStage={null}
        maxUserTurnsStage={null}
      />
      <section className="card">
        <h2>Section 1 recap</h2>
        <p className="muted small">
          Below is a short recap of what you shared in the first part of the chat, plus one number from your earlier
          survey. When you are ready, continue to the next section.
        </p>
        {card === undefined && <p className="muted">Loading…</p>}
        {card != null && (
          <div className="summary-card">
            <div className="summary-row">
              <span className="summary-label">Typical drinks last week (baseline survey)</span>
              <span className="summary-value">{drinks != null && drinks !== "" ? String(drinks) : "—"}</span>
            </div>
            {slots && (
              <>
                <div className="summary-row">
                  <span className="summary-label">Recent drinking pattern</span>
                  <span className="summary-value">{String(slots.recent_pattern ?? "—")}</span>
                </div>
                <div className="summary-row">
                  <span className="summary-label">Most concerning episode</span>
                  <span className="summary-value">{String(slots.most_concerning_episode ?? "—")}</span>
                </div>
                <div className="summary-row">
                  <span className="summary-label">Reason to cut down</span>
                  <span className="summary-value">{String(slots.reason_to_cut_down ?? "—")}</span>
                </div>
                <div className="summary-row">
                  <span className="summary-label">Importance (0–10)</span>
                  <span className="summary-value">{String(slots.importance_rating_0_10 ?? "—")}</span>
                </div>
                <div className="summary-row">
                  <span className="summary-label">Confidence (0–10)</span>
                  <span className="summary-value">{String(slots.confidence_rating_0_10 ?? "—")}</span>
                </div>
              </>
            )}
          </div>
        )}
        {err && <p className="error">{err}</p>}
        <div className="actions">
          <button type="button" className="btn" disabled={busy || card === undefined} onClick={onContinue}>
            Continue to next section
          </button>
        </div>
      </section>
    </>
  );
}
