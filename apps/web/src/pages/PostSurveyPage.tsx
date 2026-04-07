/**
 * 后测页：WAI-TECH-SF（12 项 1–7）、过程量表、操纵检验与两道开放题。
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

/** WAI-TECH-SF：1–7（1 = never, 7 = always）。 */
function Likert7({
  fieldId,
  label,
  value,
  onChange,
}: {
  fieldId: string;
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <fieldset className="likert">
      <legend>{label}</legend>
      <div className="likert-scale">
        <span className="muted small">1 Never</span>
        {[1, 2, 3, 4, 5, 6, 7].map((n) => (
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
        <span className="muted small">7 Always</span>
      </div>
    </fieldset>
  );
}

/** WAI-TECH-SF 条目（程序措辞与原文一致，将 “program” 落实为 “this text-based program”）。来源：PMC7503297，CC BY 4.0。 */
const WAI_ITEMS: { id: string; text: string }[] = [
  {
    id: "wai_tech_sf_item_01",
    text: "As a result of these sessions using this text-based program, I am clearer as to how I might be able to change.",
  },
  {
    id: "wai_tech_sf_item_02",
    text: "What I am doing with this text-based program gives me new ways of looking at my problem.",
  },
  {
    id: "wai_tech_sf_item_03",
    text: "I believe that I am a good candidate for this text-based program.",
  },
  {
    id: "wai_tech_sf_item_04",
    text: "This text-based program and I collaborate on setting goals for my therapy.",
  },
  {
    id: "wai_tech_sf_item_05",
    text: "This text-based program and I respect each other.",
  },
  {
    id: "wai_tech_sf_item_06",
    text: "This text-based program and I are working towards mutually agreed upon goals.",
  },
  {
    id: "wai_tech_sf_item_07",
    text: "I feel that this text-based program appreciates me.",
  },
  {
    id: "wai_tech_sf_item_08",
    text: "This text-based program and I agree on what is important for me to work on.",
  },
  {
    id: "wai_tech_sf_item_09",
    text: "I feel this text-based program cares about me even when I do things that it does not approve of.",
  },
  {
    id: "wai_tech_sf_item_10",
    text: "I feel that the things I do with this text-based program will help me to accomplish the changes that I want.",
  },
  {
    id: "wai_tech_sf_item_11",
    text: "This text-based program and I have established a good understanding of the kind of changes that would be good for me.",
  },
  {
    id: "wai_tech_sf_item_12",
    text: "I believe the way that this text-based program and I are working with my problem is correct.",
  },
];

function initialWai(): Record<string, number> {
  return Object.fromEntries(WAI_ITEMS.map((x) => [x.id, 4]));
}

const init5 = () => 3;

/** 后测表单与校验提交。 */
export function PostSurveyPage() {
  const navigate = useNavigate();
  const [wai, setWai] = useState(initialWai);
  const [trust, setTrust] = useState(init5);
  const [helpful, setHelpful] = useState(init5);
  const [disc, setDisc] = useState(init5);
  const [change, setChange] = useState(init5);
  const [mWarm, setMWarm] = useState(init5);
  const [mPractical, setMPractical] = useState(init5);
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
        ...wai,
        trust_1_5: trust,
        helpfulness_1_5: helpful,
        disclosure_comfort_1_5: disc,
        change_intention_1_5: change,
        manipulation_felt_warm_1_5: mWarm,
        manipulation_felt_practical_actionable_1_5: mPractical,
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
          Answer based on how you felt during this chat. Process and manipulation-check items use 1–5 (1 = strongly
          disagree / does not apply, 5 = strongly agree). For the “repetitive” item, 5 means very repetitive/scripted.
        </p>

        <h3 className="h3">Working alliance with the text program (WAI-TECH-SF)</h3>
        <p className="muted small">
          The following 12 items use a 7-point scale: 1 = never, 7 = always. (WAI-TECH-SF: Gómez Penedo et al., 2020,
          adapted from the Working Alliance Inventory—Short Form; open access via PMC7503297.)
        </p>
        {WAI_ITEMS.map((item, i) => (
          <Likert7
            key={item.id}
            fieldId={item.id}
            label={`${i + 1}. ${item.text}`}
            value={wai[item.id] ?? 4}
            onChange={(v) => setWai((prev) => ({ ...prev, [item.id]: v }))}
          />
        ))}

        <h3 className="h3">Other process measures (1–5)</h3>
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
          fieldId="m_practical"
          label="The style felt practical and focused on concrete next steps (problem-solving)."
          value={mPractical}
          onChange={setMPractical}
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
