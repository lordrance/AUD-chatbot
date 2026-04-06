/**
 * 后测页：Likert 量表与两道开放题，提交后跳转致谢页。
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import { ProgressBar } from "../components/ProgressBar";
import { HelpResourcesModal } from "../components/HelpResourcesModal";
import { loadSession, routeForStatus } from "../flow";
import { progressStepForPath } from "../flow";

/** 1–5 单选量表字段组。 */
function Likert5({
  fieldId,
  label,
  value,
  onChange,
  left,
  right,
}: {
  fieldId: string;
  label: string;
  value: number;
  onChange: (v: number) => void;
  left?: string;
  right?: string;
}) {
  return (
    <fieldset className="likert">
      <legend>{label}</legend>
      <div className="likert-scale">
        <span className="muted small">{left ?? "1"}</span>
        {[1, 2, 3, 4, 5].map((n) => (
          <label key={n} className="likert-opt">
            <input
              type="radio"
              name={fieldId}
              checked={value === n}
              onChange={() => onChange(n)}
            />
            {n}
          </label>
        ))}
        <span className="muted small">{right ?? "5"}</span>
      </div>
    </fieldset>
  );
}

/** Likert 默认值（中性）。 */
const init5 = () => 3;

/** 后测表单与校验提交。 */
export function PostSurveyPage() {
  const navigate = useNavigate();
  const [therapeutic, setTherapeutic] = useState(init5);
  const [trust, setTrust] = useState(init5);
  const [helpful, setHelpful] = useState(init5);
  const [disc, setDisc] = useState(init5);
  const [change, setChange] = useState(init5);
  const [mWarm, setMWarm] = useState(init5);
  const [mProf, setMProf] = useState(init5);
  const [mUnd, setMUnd] = useState(init5);
  const [mRep, setMRep] = useState(init5);
  const [mPer, setMPer] = useState(init5);
  const [openA, setOpenA] = useState("");
  const [openB, setOpenB] = useState("");
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
      if (st.status === "completed") navigate("/thank-you");
      else if (st.status !== "post_survey_pending") navigate(routeForStatus(st.status));
      else if (
        st.chat_summary &&
        typeof st.chat_summary === "object" &&
        Object.keys(st.chat_summary).length > 0 &&
        !sessionStorage.getItem("safechat_summary_ack")
      ) {
        navigate("/chat-summary");
      }
    });
  }, [navigate]);

  /** 校验开放题非空后 POST post-survey。 */
  async function submit() {
    const s = loadSession();
    if (!s) return;
    if (!openA.trim() || !openB.trim()) {
      setErr("Please answer both open-ended questions (brief answers are fine).");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.postPostSurvey(s.sessionId, s.token, {
        therapeutic_alliance_1_5: therapeutic,
        trust_1_5: trust,
        helpfulness_1_5: helpful,
        disclosure_comfort_1_5: disc,
        change_intention_1_5: change,
        manipulation_felt_warm_1_5: mWarm,
        manipulation_felt_professional_1_5: mProf,
        manipulation_understood_feelings_1_5: mUnd,
        manipulation_felt_repetitive_1_5: mRep,
        manipulation_felt_personal_tailored_1_5: mPer,
        open_most_helpful: openA.trim(),
        open_unnatural_or_uncomfortable: openB.trim(),
      });
      navigate("/thank-you");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ProgressBar step={progressStepForPath("/post-survey")} />
      <section className="card form-long">
        <h2>Post-survey</h2>
        <p className="muted small">
          Answer based on how you felt during this chat. Items are 1–5: 1 = strongly disagree / does not apply at all, 5
          = strongly agree / applies very much. For the “repetitive” item, 5 means very repetitive/scripted.
        </p>

        <Likert5
          fieldId="therapeutic_alliance"
          label="I felt we built a good working relationship with this text program (digital therapeutic alliance)."
          value={therapeutic}
          onChange={setTherapeutic}
          left="Strongly disagree"
          right="Strongly agree"
        />
        <Likert5
          fieldId="trust"
          label="I trusted the information and process in this conversation."
          value={trust}
          onChange={setTrust}
        />
        <Likert5
          fieldId="helpful"
          label="Overall, this conversation was helpful to me."
          value={helpful}
          onChange={setHelpful}
        />
        <Likert5
          fieldId="disc"
          label="I felt comfortable being open about drinking-related topics (disclosure comfort)."
          value={disc}
          onChange={setDisc}
        />
        <Likert5
          fieldId="change_intention"
          label="In the near future, I intend to take concrete steps to change my drinking (short-term change intention)."
          value={change}
          onChange={setChange}
        />

        <h3 className="h3">Manipulation checks (answer honestly)</h3>
        <Likert5
          fieldId="m_warm"
          label="The style felt warm and personable."
          value={mWarm}
          onChange={setMWarm}
        />
        <Likert5
          fieldId="m_prof"
          label="The style felt professional and restrained."
          value={mProf}
          onChange={setMProf}
        />
        <Likert5
          fieldId="m_und"
          label="I felt my feelings were understood."
          value={mUnd}
          onChange={setMUnd}
        />
        <Likert5
          fieldId="m_rep"
          label="The content felt repetitive or like a fixed script (higher = more repetitive/scripted)."
          value={mRep}
          onChange={setMRep}
          left="Not at all repetitive"
          right="Very repetitive"
        />
        <Likert5
          fieldId="m_per"
          label="The content felt tailored to my personal situation."
          value={mPer}
          onChange={setMPer}
        />

        <label>
          What did you find <strong>most helpful</strong>? (brief is fine)
          <textarea value={openA} onChange={(e) => setOpenA(e.target.value)} rows={3} maxLength={2000} />
        </label>
        <label>
          Was any part <strong>unnatural, uncomfortable, or awkward</strong>?
          <textarea value={openB} onChange={(e) => setOpenB(e.target.value)} rows={3} maxLength={2000} />
        </label>

        {err && <p className="error">{err}</p>}
        <div className="actions">
          <button type="button" className="btn" onClick={submit} disabled={busy}>
            Submit post-survey
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
