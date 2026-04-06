/**
 * 致谢页：流程结束说明；可选登记随访并展示可复制链接。
 */
import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import * as api from "../api";
import { ProgressBar } from "../components/ProgressBar";
import { clearSessionStorage, loadSession, routeForStatus, progressStepForPath } from "../flow";

/** 完成页与随访 opt-in UI。 */
export function ThankYouPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [fuLink, setFuLink] = useState<string | null>(null);
  const [fuErr, setFuErr] = useState<string | null>(null);
  const [fuBusy, setFuBusy] = useState(false);

  useEffect(() => {
    const s = loadSession();
    if (!s) {
      navigate("/");
      return;
    }
    api.getState(s.sessionId, s.token).then((st) => {
      if (st.status !== "completed") navigate(routeForStatus(st.status));
    });
  }, [navigate]);

  /** 至少填邮箱或电话之一后 POST followup opt-in。 */
  async function submitFollowUpOptIn() {
    const s = loadSession();
    if (!s) return;
    if (!email.trim() && !phone.trim()) {
      setFuErr("Please enter at least an email or a phone number.");
      return;
    }
    setFuBusy(true);
    setFuErr(null);
    try {
      const out = await api.postFollowUpOptIn(s.sessionId, s.token, {
        opted_in: true,
        contact_email: email.trim() || undefined,
        contact_phone: phone.trim() || undefined,
      });
      const path = out.followup_public_path.startsWith("/") ? out.followup_public_path : `/${out.followup_public_path}`;
      setFuLink(`${window.location.origin}${path}`);
    } catch (e) {
      setFuErr(e instanceof Error ? e.message : "Registration failed");
    } finally {
      setFuBusy(false);
    }
  }

  return (
    <>
      <ProgressBar step={progressStepForPath("/thank-you")} />
      <section className="card">
        <h2>Thank you</h2>
        <p>
          You have finished this study session. Data will be used for research only; this program does{" "}
          <strong>not</strong> provide individualized medical advice or ongoing treatment.
        </p>
        <div className="followup-box">
          <h3 className="h3">Optional 7-day follow-up</h3>
          <p className="muted small">
            If you wish, leave contact info and <strong>save the private link below</strong> to open a very short
            survey in about seven days. There is no automated email/SMS in this build—follow your ethics approval.
          </p>
          <label className="field">
            Email (optional)
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          </label>
          <label className="field">
            Phone (optional)
            <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" />
          </label>
          {fuErr && <p className="error">{fuErr}</p>}
          {fuLink && (
            <p className="notice">
              <strong>Save this follow-up link:</strong>
              <br />
              <code className="fu-link">{fuLink}</code>
            </p>
          )}
          <button type="button" className="btn secondary" disabled={fuBusy} onClick={submitFollowUpOptIn}>
            {fuBusy ? "Submitting…" : fuLink ? "Registered (you can copy the link again)" : "Register and create link"}
          </button>
        </div>
        <p className="muted small">You may close the browser; contact the study team for technical support.</p>
        <div className="actions">
          <button
            type="button"
            className="btn secondary"
            onClick={() => {
              clearSessionStorage();
              navigate("/");
            }}
          >
            End and clear session
          </button>
          <Link to="/" className="btn tertiary">
            Back to home
          </Link>
        </div>
      </section>
    </>
  );
}
