/**
 * 不合格说明页：展示服务端聚合的 ineligible_reason 与资源入口。
 */
import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import * as api from "../api";
import { HelpResourcesModal } from "../components/HelpResourcesModal";
import { loadSession, routeForStatus, clearSessionStorage } from "../flow";

/** 不合格终态展示。 */
export function IneligiblePage() {
  const navigate = useNavigate();
  const [reason, setReason] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);

  useEffect(() => {
    const s = loadSession();
    if (!s) {
      navigate("/");
      return;
    }
    api.getState(s.sessionId, s.token).then((st) => {
      if (st.status !== "ineligible") {
        navigate(routeForStatus(st.status));
        return;
      }
      setReason(st.ineligible_reason);
    });
  }, [navigate]);

  return (
    <>
      <section className="card">
        <h2>You are not eligible for this study session</h2>
        <p>Thank you for your time and honest answers. Under the preset rules, this session cannot continue.</p>
        {reason && (
          <div className="consent-box">
            <p>
              <strong>Note:</strong>
              {reason}
            </p>
          </div>
        )}
        <p className="muted small">
          If you need health or emotional support, use Help & resources below or contact local services and crisis
          lines.
        </p>
        <div className="actions">
          <button type="button" className="btn" onClick={() => setHelpOpen(true)}>
            Help & resources
          </button>
          <button
            type="button"
            className="btn secondary"
            onClick={() => {
              clearSessionStorage();
              navigate("/");
            }}
          >
            Home and clear session
          </button>
          <Link to="/" className="btn tertiary">
            Back to home
          </Link>
        </div>
      </section>
      <HelpResourcesModal open={helpOpen} onClose={() => setHelpOpen(false)} />
    </>
  );
}
