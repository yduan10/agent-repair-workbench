import Link from "next/link";
import { ChevronRight } from "lucide-react";

export type Crumb = { label: string; href?: string };

export function PageHeader({ title, description, badge, actions, crumbs }: {
  title: React.ReactNode; description?: React.ReactNode; badge?: React.ReactNode; actions?: React.ReactNode; crumbs?: Crumb[];
}) {
  return <header className="page-header">
    <div>
      {crumbs && crumbs.length > 0 && <nav className="page-header-crumbs" aria-label="位置">
        {crumbs.map((crumb, index) => <span key={`${crumb.label}-${index}`} style={{ display: "contents" }}>
          {index > 0 && <ChevronRight size={12} aria-hidden="true" />}
          {crumb.href ? <Link href={crumb.href}>{crumb.label}</Link> : <span aria-current="page">{crumb.label}</span>}
        </span>)}
      </nav>}
      {/* The badge sits beside the h1, not inside it, so the heading's accessible name is just the page title. */}
      <div className="page-header-title"><h1>{title}</h1>{badge}</div>
      {description && <p className="page-header-desc">{description}</p>}
    </div>
    {actions && <div className="page-header-actions">{actions}</div>}
  </header>;
}
