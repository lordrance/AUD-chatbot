/**
 * 顶部进度条：按 flow 步数显示百分比；聊天步骤可附带子阶段提示。
 */
type Props = {
  step: number;
  /** Total steps including summary, post-survey, thank-you (default 8) */
  total?: number;
  chatStage?: number | null;
};

/** 渲染条形进度与文字标签；step≤0 时不显示。 */
export function ProgressBar({ step, total = 8, chatStage }: Props) {
  if (step <= 0) return null;
  const pct = Math.min(100, Math.round((step / total) * 100));
  const chatHint =
    chatStage != null && step === 5 ? ` (chat segment ${chatStage + 1}/5 · system-controlled)` : "";
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
