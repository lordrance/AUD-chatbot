/**
 * 基线问卷：饮酒量、改变准备度与可选关注短语，提交后进入随机分组页。
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import { ProgressBar } from "../components/ProgressBar";
import { HelpResourcesModal } from "../components/HelpResourcesModal";
import { loadSession, routeForStatus, progressStepForPath } from "../flow";

/** 基线表单根组件。 */
export function BaselinePage() {
  const navigate = useNavigate();
  const [drinks, setDrinks] = useState(12);
  const [readiness, setReadiness] = useState(6);
  const [concern, setConcern] = useState("");
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
      if (st.status !== "baseline_pending") navigate(routeForStatus(st.status));
    });
  }, [navigate]);

  /** POST baseline 并导航 /randomize。 */
  async function submit() {
    const s = loadSession();
    if (!s) return;
    setBusy(true);
    setErr(null);
    try {
      const body: Record<string, unknown> = {
        typical_drinks_last_week: drinks,
        readiness_to_change_1_10: readiness,
      };
      const c = concern.trim();
      if (c) body.primary_concern_short = c;
      await api.postBaseline(s.sessionId, s.token, body);
      navigate("/randomize");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ProgressBar step={progressStepForPath("/baseline")} />
      <section className="card">
        <h2>Baseline survey</h2>
        <label>
          Approximate standard drinks last week (0–1000)
          <input
            type="number"
            min={0}
            max={1000}
            step={0.5}
            value={drinks}
            onChange={(e) => setDrinks(Number(e.target.value))}
          />
        </label>
        <label>
          Readiness to change (1–10; 1 = not ready, 10 = ready to act)
          <input
            type="range"
            min={1}
            max={10}
            value={readiness}
            onChange={(e) => setReadiness(Number(e.target.value))}
          />
          <span className="range-val">{readiness}</span>
        </label>
        <label>
          One sentence about what worries you most (optional, max 500 characters)
          <textarea
            value={concern}
            maxLength={500}
            rows={3}
            onChange={(e) => setConcern(e.target.value)}
          />
        </label>
        {err && <p className="error">{err}</p>}
        <div className="actions">
          <button type="button" className="btn" onClick={submit} disabled={busy}>
            Submit and continue
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
