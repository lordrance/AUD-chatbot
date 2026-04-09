/**
 * 对话摘要卡：展示服务端 chat_summary，确认后进入后测。
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import { ProgressBar } from "../components/ProgressBar";
import { loadSession, routeForStatus, progressStepForPath } from "../flow";

const SUMMARY_ACK = "safechat_summary_ack";

/** 渲染摘要键值一行；空值显示为 —。 */
function line(label: string, value: string | number | null | undefined) {
  const v =
    value === null || value === undefined || (typeof value === "string" && !value.trim()) ? "—" : String(value);
  return (
    <div className="summary-row">
      <span className="summary-label">{label}</span>
      <span className="summary-value">{v}</span>
    </div>
  );
}

/** 摘要只读展示与「继续后测」导航。 */
export function ChatSummaryPage() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<Record<string, unknown> | null | undefined>(undefined);

  useEffect(() => {
    const s = loadSession();
    if (!s) {
      navigate("/");
      return;
    }
    api.getState(s.sessionId, s.token).then((st) => {
      if (st.status === "completed") {
        navigate("/thank-you");
        return;
      }
      if (st.status !== "post_survey_pending") {
        navigate(routeForStatus(st.status));
        return;
      }
      const raw = st.chat_summary;
      setSummary(
        raw != null && typeof raw === "object" ? (raw as Record<string, unknown>) : {},
      );
    });
  }, [navigate]);

  /** 标记已阅摘要并进入后测路由。 */
  function continuePost() {
    sessionStorage.setItem(SUMMARY_ACK, "1");
    navigate("/post-survey");
  }

  return (
    <>
      <ProgressBar step={progressStepForPath("/chat-summary")} />
      <section className="card">
        <h2>Chat summary</h2>
        <p className="muted small">
          Structured recap from your chat responses before the post-survey (data use as described in consent).
        </p>
        {summary === undefined && <p className="muted">Loading…</p>}
        {summary != null && Object.keys(summary).length === 0 && (
          <p className="muted">No summary fields yet—you can still continue to the post-survey.</p>
        )}
        {summary != null && Object.keys(summary).length > 0 && (
          <div className="summary-card">
            {line("Preferred name", summary.preferred_name as string | undefined)}
            {line("Main reason to cut down", (summary.summary_reason ?? summary.top_reason_to_cut_down) as string | undefined)}
            {line(
              "Main trigger / high-risk situation",
              (summary.summary_trigger ?? summary.top_trigger_high_risk_situation) as string | undefined,
            )}
            {line("Situation details (who/where/when/cues)", summary.trigger_context as string | undefined)}
            {line("Strategy focus", (summary.selected_strategy ?? summary.support_focus) as string | undefined)}
            {line("Chosen plan (if–then)", (summary.summary_plan ?? summary.micro_plan_if_then) as string | undefined)}
            {line("Closing confidence (0–10)", summary.summary_confidence as number | undefined)}
            {line("Confidence / readiness notes", summary.confidence_summary as string | undefined)}
            {line("Optional closing note", summary.optional_takeaway as string | undefined)}
          </div>
        )}
        <div className="actions">
          <button type="button" className="btn" onClick={continuePost} disabled={summary === undefined}>
            Continue to post-survey
          </button>
        </div>
      </section>
    </>
  );
}
