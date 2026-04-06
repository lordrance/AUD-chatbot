/**
 * 帮助与资源模态：默认文案与安全终止时的补充说明 variant。
 */
type Props = {
  open: boolean;
  onClose: () => void;
  /** Extra copy when chat ended by safety policy */
  variant?: "default" | "termination";
};

/** 受控弹层；open 为 false 时不渲染。 */
export function HelpResourcesModal({ open, onClose, variant = "default" }: Props) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="help-title">
      <div className="modal-panel">
        <h2 id="help-title">Help & resources</h2>
        {variant === "termination" && (
          <p className="muted">
            The study chat may end early because of platform safety rules; that <strong>does not</strong> mean you were
            individually assessed. For urgent risk, rely on real-world services.
          </p>
        )}
        <p className="modal-warning">
          <strong>Chats on this site are not continuously monitored.</strong> If you are at imminent risk of harming
          yourself or others, or you have acute withdrawal symptoms, contact local emergency services immediately or go
          to the nearest emergency department.
        </p>
        <p>
          This research tool <strong>cannot replace</strong> psychotherapy, crisis intervention, or medical withdrawal
          management.
        </p>
        <ul className="resource-list">
          <li>
            Examples of support lines (use what is current in your area): national/regional crisis lines, campus
            counseling centers.
          </li>
          <li>For alcohol-related health information, follow guidance from licensed clinicians or public health agencies.</li>
        </ul>
        <p className="muted small">Close this window anytime to continue or leave the study flow; seeking help is your choice.</p>
        <button type="button" className="btn secondary" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}
