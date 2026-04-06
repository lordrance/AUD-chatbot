/**
 * 公开随访页：路由参数 token，无需登录会话即可 GET 状态 / POST 提交。
 */
import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import * as api from "../api";

/** 7 天随访问卷独立入口。 */
export function FollowUpPage() {
  const { token } = useParams<{ token: string }>();
  const [state, setState] = useState<Awaited<ReturnType<typeof api.getFollowUpState>> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [drinkDays, setDrinkDays] = useState(0);
  const [heavyDays, setHeavyDays] = useState(0);
  const [usedPlan, setUsedPlan] = useState<"yes" | "no" | "somewhat">("somewhat");
  const [confidence, setConfidence] = useState(5);
  const [willing, setWilling] = useState(3);

  useEffect(() => {
    if (!token) return;
    api
      .getFollowUpState(token)
      .then(setState)
      .catch(() => setErr("Could not load the follow-up form."));
  }, [token]);

  /** POST 随访表单并刷新本地 state。 */
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setErr(null);
    try {
      await api.postFollowUpSurvey(token, {
        drinking_days_last_7: drinkDays,
        heavy_drinking_days_last_7: heavyDays,
        used_plan: usedPlan,
        intention_confidence_reduce_1_10: confidence,
        willing_to_use_again_1_5: willing,
      });
      setState(await api.getFollowUpState(token));
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  }

  if (!token) return <p className="error">Missing follow-up token.</p>;
  if (!state) return <p className="muted">{err ?? "Loading…"}</p>;

  if (state.already_submitted) {
    return (
      <section className="card">
        <h2>Follow-up submitted</h2>
        <p>Thank you. The study team will handle data according to ethics requirements.</p>
      </section>
    );
  }

  if (!state.can_submit) {
    return (
      <section className="card">
        <h2>Not available yet</h2>
        <p className="muted">
          Please confirm you completed the main study. If this page still fails, contact the research team.
        </p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>7-day brief follow-up</h2>
      <p className="muted small">Standalone link—no login. Data are used for research summaries only.</p>
      {err && <p className="error">{err}</p>}
      <form onSubmit={submit}>
        <label className="field">
          Drinking days in the last 7 days (0–7)
          <input
            type="number"
            min={0}
            max={7}
            value={drinkDays}
            onChange={(e) => setDrinkDays(Number(e.target.value))}
          />
        </label>
        <label className="field">
          Heavy drinking days (0–7, ≤ above)
          <input
            type="number"
            min={0}
            max={7}
            value={heavyDays}
            onChange={(e) => setHeavyDays(Number(e.target.value))}
          />
        </label>
        <label className="field">
          Did you use the small plan from the chat?
          <select value={usedPlan} onChange={(e) => setUsedPlan(e.target.value as typeof usedPlan)}>
            <option value="yes">Yes</option>
            <option value="somewhat">Somewhat</option>
            <option value="no">No</option>
          </select>
        </label>
        <label className="field">
          Current intention/confidence to reduce drinking (1–10)
          <input
            type="number"
            min={1}
            max={10}
            value={confidence}
            onChange={(e) => setConfidence(Number(e.target.value))}
          />
        </label>
        <label className="field">
          Willingness to use this program again if you could (1–5)
          <input
            type="number"
            min={1}
            max={5}
            value={willing}
            onChange={(e) => setWilling(Number(e.target.value))}
          />
        </label>
        <button type="submit" className="btn" disabled={busy}>
          {busy ? "Submitting…" : "Submit"}
        </button>
      </form>
    </section>
  );
}
