import type { LucideIcon } from "lucide-react";

export function EmptyState({ icon: Icon, title, children, actions, align }: {
  icon?: LucideIcon; title: string; children?: React.ReactNode; actions?: React.ReactNode; align?: "center";
}) {
  return <div className="empty-state" data-align={align}>
    {Icon && <span className="empty-icon"><Icon size={18} aria-hidden="true" /></span>}
    <h3>{title}</h3>
    {children && <p>{children}</p>}
    {actions && <div className="empty-actions">{actions}</div>}
  </div>;
}
