/**
 * 资格筛查页：AUDIT-C 与纳入条件，通过后进入基线。
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import { ProgressBar } from "../components/ProgressBar";
import { HelpResourcesModal } from "../components/HelpResourcesModal";
import { loadSession, routeForStatus, progressStepForPath } from "../flow";

/** 资格表单与提交逻辑。 */
export function EligibilityPage() {
  const navigate = useNavigate();
  const [age, setAge] = useState(25);
  const [sex, setSex] = useState<"male" | "female" | "other">("male");
  const [freq, setFreq] = useState(2);
  const [qty, setQty] = useState(2);
  const [binge, setBinge] = useState(2);
  const [wantsReduce, setWantsReduce] = useState(true);
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
      if (st.status !== "eligibility_pending") navigate(routeForStatus(st.status));
    });
  }, [navigate]);

  /** POST 筛查结果；不通过则跳转不合格页。 */
  async function submit() {
    const s = loadSession();
    if (!s) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await api.postEligibility(s.sessionId, s.token, {
        age_years: age,
        sex_at_birth: sex,
        audit_c_frequency: freq,
        audit_c_typical_quantity: qty,
        audit_c_binge: binge,
        wants_to_reduce_drinking: wantsReduce,
      });
      if (res.ok === false) {
        navigate("/ineligible");
        return;
      }
      navigate("/baseline");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ProgressBar step={progressStepForPath("/eligibility")} />
      <section className="card">
        <h2>Eligibility screening</h2>
        <p className="muted">Each AUDIT-C item is scored 0–4; inclusion is decided on the server using the study threshold.</p>
        <label>
          Age (years)
          <input
            type="number"
            min={18}
            max={120}
            value={age}
            onChange={(e) => setAge(Number(e.target.value))}
          />
        </label>
        <fieldset>
          <legend>Sex assigned at birth</legend>
          <label>
            <input type="radio" name="sex" checked={sex === "male"} onChange={() => setSex("male")} /> Male
          </label>
          <label>
            <input type="radio" name="sex" checked={sex === "female"} onChange={() => setSex("female")} /> Female
          </label>
          <label>
            <input type="radio" name="sex" checked={sex === "other"} onChange={() => setSex("other")} /> Other /
            prefer not to say
          </label>
        </fieldset>
        <label>
          Drinking frequency (AUDIT-C Q1, 0–4)
          <select value={freq} onChange={(e) => setFreq(Number(e.target.value))}>
            {[0, 1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label>
          Typical quantity (Q2, 0–4)
          <select value={qty} onChange={(e) => setQty(Number(e.target.value))}>
            {[0, 1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label>
          Binge frequency (Q3, 0–4)
          <select value={binge} onChange={(e) => setBinge(Number(e.target.value))}>
            {[0, 1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={wantsReduce}
            onChange={(e) => setWantsReduce(e.target.checked)}
          />
          I want to reduce my drinking (required for inclusion)
        </label>
        {err && <p className="error">{err}</p>}
        <div className="actions">
          <button type="button" className="btn" onClick={submit} disabled={busy}>
            Submit screening
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
