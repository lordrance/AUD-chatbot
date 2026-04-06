/**
 * 顶部进度条：按 flow 步数显示百分比；聊天步骤可附带「聊天小节 1/4–4/4」与轮次上限提示。
 */
type Props = {
  step: number;
  /** Total steps including summary, post-survey, thank-you (default 8) */
  total?: number;
  /** Legacy FSM stage 0–4 (optional) */
  chatStage?: number | null;
  /** 聊天专用四段进度（与整流程 step 独立） */
  chatSectionOfFour?: number | null;
  userTurnsInStage?: number | null;
  maxUserTurnsStage?: number | null;
};

/** 渲染条形进度与文字标签；step≤0 时不显示。 */
export function ProgressBar({
  step,
  total = 8,
  chatStage,
  chatSectionOfFour,
  userTurnsInStage,
  maxUserTurnsStage,
}: Props) {
  if (step <= 0) return null;
  const pct = Math.min(100, Math.round((step / total) * 100));
  const showChatSection = chatSectionOfFour != null && step === 5;
  const turnHint =
    userTurnsInStage != null && maxUserTurnsStage != null
      ? ` · turns this section ${userTurnsInStage}/${maxUserTurnsStage}`
      : "";
  const chatHint = showChatSection
    ? ` · chat section ${chatSectionOfFour}/4 (system-controlled)${turnHint}`
    : chatStage != null && step === 5
      ? ` (FSM stage ${chatStage + 1}/5)`
      : "";
  return (
    <div className="progress-wrap" aria-label="Study flow progress">
      <div className="progress-bar-outer">
        <div className="progress-bar-inner" style={{ width: `${pct}%` }} />
      </div>
      <p className="progress-label">
        Progress: step {step} / {total}
        {chatHint}
      </p>
    </div>
  );
}
