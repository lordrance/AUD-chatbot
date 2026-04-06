/**
 * 安全结束页：会话为 abandoned 时展示固定说明，并可打开资源弹窗。
 */
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import * as api from "../api";
import { HelpResourcesModal } from "../components/HelpResourcesModal";
import { loadSession, routeForStatus } from "../flow";

/** 安全策略导致的流程终止页。 */
export function SafetyEndPage() {
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const reason = search.get("reason") ?? "policy";
  const [helpOpen, setHelpOpen] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);

  useEffect(() => {
    const s = loadSession();
    if (!s) {
      navigate("/");
      return;
    }
    api
      .getState(s.sessionId, s.token)
      .then((st) => {
        if (st.status !== "abandoned") {
          navigate(routeForStatus(st.status));
          return;
        }
        if (st.dropout_stage) setDetail(st.dropout_stage);
      })
      .catch(() => navigate("/"));
  }, [navigate]);

  const title =
    reason === "pre_chat"
      ? "You cannot enter the chat under current safety rules"
      : "This research chat ended under safety rules";

  return (
    <>
      <section className="card">
        <h2>{title}</h2>
        <p className="modal-warning">
          <strong>This system is not continuously monitored and cannot provide emergency care or treatment.</strong> If
          you or someone else is in immediate danger, call local emergency services (e.g. 911 / 999 / 112) or go to the
          nearest emergency department.
        </p>
        <p>
          This program is a <strong>research tool</strong>. It does not replace counseling, psychiatric care, or medical
          detox. Tap below for general resource pointers (illustrative only; not an endorsement).
        </p>
        {detail && (
          <p className="muted small">
            Internal dropout code (for the study team): <code>{detail}</code>
          </p>
        )}
        <div className="actions">
          <button type="button" className="btn" onClick={() => setHelpOpen(true)}>
            Open help & resources
          </button>
          <button type="button" className="btn tertiary" onClick={() => navigate("/")}>
            Back to home
          </button>
        </div>
      </section>
      <HelpResourcesModal variant="termination" open={helpOpen} onClose={() => setHelpOpen(false)} />
    </>
  );
}
