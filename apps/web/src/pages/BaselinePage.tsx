/**
 * 基线问卷：饮酒、准备度、重要性、人口学简要、AI 使用与治疗状态等。
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import { ProgressBar } from "../components/ProgressBar";
import { HelpResourcesModal } from "../components/HelpResourcesModal";
import { loadSession, routeForStatus, progressStepForPath } from "../flow";

type Edu = "less_than_hs" | "hs_ged" | "some_college" | "college_grad" | "grad_prof" | "prefer_not";
type Emp = "employed" | "student" | "unemployed" | "retired" | "other" | "prefer_not";
type AiUse = "never" | "rarely" | "sometimes" | "often";

/** 基线表单根组件。 */
export function BaselinePage() {
  const navigate = useNavigate();
  const [drinks, setDrinks] = useState(12);
  const [readiness, setReadiness] = useState(6);
  const [importance, setImportance] = useState(7);
  const [priorAi, setPriorAi] = useState<AiUse>("never");
  const [inTreatment, setInTreatment] = useState(false);
  const [treatmentNotes, setTreatmentNotes] = useState("");
  const [education, setEducation] = useState<Edu>("college_grad");
  const [employment, setEmployment] = useState<Emp>("employed");
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
        importance_to_reduce_0_10: importance,
        prior_chatbot_or_ai_use: priorAi,
        in_treatment_for_aud_or_mental_health: inTreatment,
        education_level: education,
        employment_status: employment,
      };
      const tn = treatmentNotes.trim();
      if (tn) body.treatment_notes = tn;
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
          Importance of cutting down <strong>right now</strong> (0–10)
          <input
            type="range"
            min={0}
            max={10}
            value={importance}
            onChange={(e) => setImportance(Number(e.target.value))}
          />
          <span className="range-val">{importance}</span>
        </label>
        <label>
          Prior use of chatbots or AI for health or habits
          <select value={priorAi} onChange={(e) => setPriorAi(e.target.value as AiUse)}>
            <option value="never">Never</option>
            <option value="rarely">Rarely</option>
            <option value="sometimes">Sometimes</option>
            <option value="often">Often</option>
          </select>
        </label>
        <label className="checkbox-row">
          <input type="checkbox" checked={inTreatment} onChange={(e) => setInTreatment(e.target.checked)} />I am currently in
          treatment for alcohol use and/or mental health
        </label>
        <label>
          Treatment notes (optional, max 500 characters)
          <textarea value={treatmentNotes} maxLength={500} rows={2} onChange={(e) => setTreatmentNotes(e.target.value)} />
        </label>
        <label>
          Highest education
          <select value={education} onChange={(e) => setEducation(e.target.value as Edu)}>
            <option value="less_than_hs">Less than high school</option>
            <option value="hs_ged">High school / GED</option>
            <option value="some_college">Some college</option>
            <option value="college_grad">College graduate</option>
            <option value="grad_prof">Graduate / professional degree</option>
            <option value="prefer_not">Prefer not to say</option>
          </select>
        </label>
        <label>
          Employment status
          <select value={employment} onChange={(e) => setEmployment(e.target.value as Emp)}>
            <option value="employed">Employed</option>
            <option value="student">Student</option>
            <option value="unemployed">Unemployed</option>
            <option value="retired">Retired</option>
            <option value="other">Other</option>
            <option value="prefer_not">Prefer not to say</option>
          </select>
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
