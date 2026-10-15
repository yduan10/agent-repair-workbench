import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";

const icons = { neutral: Info, pass: CheckCircle2, fail: XCircle, unknown: AlertTriangle };

export function Callout({ tone = "neutral", title, children, actions, role }: {
  tone?: keyof typeof icons; title?: React.ReactNode; children?: React.ReactNode; actions?: React.ReactNode; role?: "alert" | "status";
}) {
  const Icon = icons[tone];
  return <div className="callout" data-tone={tone === "neutral" ? undefined : tone} role={role}>
    <Icon size={15} aria-hidden="true" />
    <div className="callout-body">{title && <strong>{title}</strong>}{children && <div>{children}</div>}</div>
    {actions && <div className="callout-actions">{actions}</div>}
  </div>;
}
