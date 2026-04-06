/**
 * 知情同意页：加载服务端 Markdown、勾选确认后提交 consent。
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import { ProgressBar } from "../components/ProgressBar";
import { HelpResourcesModal } from "../components/HelpResourcesModal";
import { loadSession, routeForStatus, progressStepForPath } from "../flow";

/** 知情同意流程 UI。 */
export function ConsentPage() {
  const navigate = useNavigate();
  const [version, setVersion] = useState<string | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [consentBody, setConsentBody] = useState<string | null>(null);
  const [consentLoadErr, setConsentLoadErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .getConsentDocument()
      .then((d) => {
        setConsentBody(d.body);
        setConsentLoadErr(null);
      })
      .catch(() => setConsentLoadErr("Could not load the consent text. Refresh or try again later."));
  }, []);

  useEffect(() => {
    const s = loadSession();
    if (!s) {
      navigate("/");
      return;
    }
    api
      .getState(s.sessionId, s.token)
      .then((st) => {
        if (st.status !== "consent_pending") {
          navigate(routeForStatus(st.status));
          return;
        }
        setVersion(st.expected_consent_version);
      })
      .catch(() => navigate("/"));
  }, [navigate]);

  /** 校验勾选与版本后 POST consent。 */
  async function submit() {
    const s = loadSession();
    if (!s || !version) return;
    if (!accepted) {
      setErr('Please check "I have read and agree".');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.postConsent(s.sessionId, s.token, {
        consent_accepted: true,
        consent_document_version: version,
      });
      navigate("/eligibility");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ProgressBar step={progressStepForPath("/consent")} />
      <section className="card">
        <h2>Informed consent</h2>
        <p className="muted">
          Server document version: <strong>{version ?? "Loading…"}</strong>
          {consentBody && version && consentBody.includes(version) === false && (
            <span> (Body text and version constant should match; see docs/consent-versioning.md)</span>
          )}
        </p>
        {consentLoadErr && <p className="error">{consentLoadErr}</p>}
        <div className="consent-box">
          <p className="muted small">
            <strong>Not treatment / not emergency care:</strong> this program does not diagnose, treat, or provide
            real-time crisis services. The chat is <strong>not</strong> continuously monitored. In an emergency, use
            local emergency services and professional help (see Help & resources).
          </p>
          <article
            className="consent-markdown"
            style={{ whiteSpace: "pre-wrap", maxHeight: "min(60vh, 28rem)", overflow: "auto" }}
          >
            {consentBody ?? "Loading consent text…"}
          </article>
        </div>
        <label className="checkbox-row">
          <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />I have read and
          understand the full text above and agree to take part in this study (version {version ?? "—"}).
        </label>
        {err && <p className="error">{err}</p>}
        <div className="actions">
          <button type="button" className="btn" onClick={submit} disabled={busy || !version || !consentBody}>
            Submit consent
          </button>
          <button type="button" className="btn tertiary" onClick={() => setHelpOpen(true)}>
            Help & resources
          </button>
        </div>
      </section>
      <HelpResourcesModal open={helpOpen} onClose={() => setHelpOpen(false)} />
    </>
  );
}
