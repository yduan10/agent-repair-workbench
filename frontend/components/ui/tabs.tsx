import Link from "next/link";

export type TabItem = { key: string; label: React.ReactNode; href: string; count?: number };

/** URL-driven tabs: each tab is a link so state survives reload and Back. */
export function LinkTabs({ items, active, label }: { items: TabItem[]; active: string; label: string }) {
  return <nav className="tabs" aria-label={label}>
    {items.map(item => <Link key={item.key} href={item.href} scroll={false} aria-current={item.key === active ? "page" : undefined}>
      {item.label}{item.count !== undefined && <span className="subtle tabular">{item.count}</span>}
    </Link>)}
  </nav>;
}
