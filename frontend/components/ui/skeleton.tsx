export function Skeleton({ width = "100%", height = 12 }: { width?: number | string; height?: number }) {
  return <span className="skeleton" style={{ width, height }} aria-hidden="true" />;
}
export function SkeletonRows({ rows = 4, label = "正在加载…" }: { rows?: number; label?: string }) {
  return <div className="skeleton-rows" role="status" aria-busy="true">
    <span className="sr-only">{label}</span>
    {Array.from({ length: rows }, (_, i) => <div key={i} style={{ display: "grid", gap: 6 }}>
      <Skeleton width={`${60 - (i % 3) * 12}%`} height={13} /><Skeleton width={`${34 + (i % 2) * 10}%`} height={10} />
    </div>)}
  </div>;
}
