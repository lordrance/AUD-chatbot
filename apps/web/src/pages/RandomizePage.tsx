/**
 * 随机分组页：调用 POST randomize；403 时跳转安全说明页。
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import { ProgressBar } from "../components/ProgressBar";
import { HelpResourcesModal } from "../components/HelpResourcesModal";
import { loadSession, routeForStatus, progressStepForPath } from "../flow";

/** 随机分组入口按钮与状态校验。 */
export function RandomizePage() {
  const navigate = useNavigate();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  useEffect(() => {
    const s = loadSession();
    if (!s) {
      navigate("/");
      return;
    }
    api.getState(s.sessionId, s.token).then((st) => {
      if (st.status === "chat_ready" || st.status === "chat_active") navigate("/chat");
      else if (st.status !== "pending_randomization") navigate(routeForStatus(st.status));
    });
  }, [navigate]);

  /** 请求随机分配并进入聊天；安全拦截时走 /safety-end。 */
  async function randomize() {
    const s = loadSession();
    if (!s) return;
    setBusy(true);
    setErr(null);
    try {
      await api.postRandomize(s.sessionId, s.token);
      navigate("/chat");
    } catch (e) {
      if (e instanceof api.HttpError && e.status === 403) {
        navigate("/safety-end?reason=pre_chat");
        return;
      }
      setErr(e instanceof Error ? e.message : "Randomization failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ProgressBar step={progressStepForPath("/randomize")} />
      <section className="card">
        <h2>Start the chat</h2>
        <p>
          Baseline is complete. Tap below to be randomly assigned to a conversation condition and begin the text chat
          (about 20–25 minutes).
        </p>
        <p className="muted small">To preserve study blinding, your exact condition name is not shown here.</p>
        {err && <p className="error">{err}</p>}
        <div className="actions">
          <button type="button" className="btn" onClick={randomize} disabled={busy}>
            {busy ? "Working…" : "I'm ready — start chat"}
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
