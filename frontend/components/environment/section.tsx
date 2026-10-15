import { CopyButton } from "../ui/copy-id";

/** One settings section with a deep-link id. */
export function EnvSection({ id, title, description, actions, children }: {
  id: string; title: string; description?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode;
}) {
  return <section id={id} className="env-section" aria-labelledby={`${id}-title`}>
    <div className="env-section-head">
      <div>
        <h2 id={`${id}-title`}>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="env-section-actions">{actions}</div>}
    </div>
    {children}
  </section>;
}

/** Label / value row inside a settings pane. */
export function SettingRow({ label, children, aside }: { label: React.ReactNode; children: React.ReactNode; aside?: React.ReactNode }) {
  return <div className="setting-row">
    <div className="setting-label">{label}</div>
    <div className="setting-value">{children}</div>
    {aside && <div className="setting-aside">{aside}</div>}
  </div>;
}

/** A shell command shown in mono with one-click copy. */
export function Command({ value, label = "命令" }: { value: string; label?: string }) {
  return <div className="env-command">
    <code translate="no">{value}</code>
    <CopyButton value={value} label={label} className="btn btn-ghost btn-sm btn-icon" />
  </div>;
}

/** A variable or other short identifier with one-click copy. */
export function CopyCode({ value, label }: { value: string; label: string }) {
  return <span className="env-copy-code"><code translate="no">{value}</code><CopyButton value={value} label={label} className="btn btn-ghost btn-sm btn-icon" /></span>;
}
