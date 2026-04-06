/**
 * 落地页：研究说明、创建新会话或恢复本地保存的会话。
 */
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import * as api from "../api";
import { HelpResourcesModal } from "../components/HelpResourcesModal";
import { loadSession, routeForStatus, saveSession } from "../flow";

/** 落地页根组件。 */
export function LandingPage() {
  const navigate = useNavigate();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  /** 用已存 token 拉取 state 并导航到对应步骤。 */
  async function resume() {
    const s = loadSession();
    if (!s) return;
    setBusy(true);
    setErr(null);
    try {
      const st = await api.getState(s.sessionId, s.token);
      navigate(routeForStatus(st.status));
    } catch {
      setErr("Could not restore your session. Please start again.");
    } finally {
      setBusy(false);
    }
  }

  /** POST 新会话并写入 localStorage，进入同意书。 */
  async function startNew() {
    setBusy(true);
    setErr(null);
    try {
      const { session_id, session_token } = await api.createSession();
      saveSession(session_id, session_token);
      navigate("/consent");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to create session");
    } finally {
      setBusy(false);
    }
  }

  const hasSaved = !!loadSession();

  return (
    <>
      <header className="page-header">
        <h1>SafeChat-AUD</h1>
        <p className="tagline">Research text chat · single session · not a treatment product</p>
      </header>

      <section className="card">
        <h2>What this is</h2>
        <p>
          This site is for <strong>research</strong>: a structured text conversation plus short surveys. It usually
          takes about <strong>20–25 minutes</strong>.
        </p>
        <p>
          It does <strong>not</strong> replace medical care, therapy, or crisis services. The chat is{" "}
          <strong>not</strong> continuously monitored by staff.
        </p>
        <ul>
          <li>You will read informed consent, then screening and baseline questions;</li>
          <li>Then a text dialogue (stages are controlled by the system);</li>
          <li>Finally a short post-survey to finish.</li>
        </ul>
        {err && <p className="error">{err}</p>}
        <div className="actions">
          <button type="button" className="btn" onClick={startNew} disabled={busy}>
            {busy ? "Please wait…" : "I understand — start a new session"}
          </button>
          {hasSaved && (
            <button type="button" className="btn secondary" onClick={resume} disabled={busy}>
              Continue my saved session
            </button>
          )}
          <button type="button" className="btn tertiary" onClick={() => setHelpOpen(true)}>
            Help & resources
          </button>
        </div>
      </section>
      <HelpResourcesModal open={helpOpen} onClose={() => setHelpOpen(false)} />
    </>
  );
}
