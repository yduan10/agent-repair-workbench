import type { CheckTone } from "../../lib/environment";

export type Tone = CheckTone | "accent";

export function StatusDot({ tone, label }: { tone: Tone; label?: string }) {
  return <span className="status-dot" data-tone={tone} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true} />;
}

/** Verdict/status badge. Colour encodes the result only; text always carries the meaning. */
export function StatusBadge({ tone, children, dot = true, variant }: { tone: Tone; children: React.ReactNode; dot?: boolean; variant?: "outline" }) {
  return <span className="badge" data-tone={tone} data-variant={variant}>{dot && <StatusDot tone={tone} />}{children}</span>;
}
