"use client";
import { useSyncExternalStore } from "react";
import { formatDateTime, formatRelative, toDate, type TimeInput } from "../../lib/format";

let listeners = new Set<() => void>();
let tick = 0;
let timer: number | undefined;
function subscribe(callback: () => void) {
  listeners.add(callback);
  if (timer === undefined) timer = window.setInterval(() => { tick += 1; listeners.forEach(l => l()); }, 30000);
  return () => {
    listeners.delete(callback);
    if (listeners.size === 0) { window.clearInterval(timer); timer = undefined; listeners = new Set(); }
  };
}

/** Relative time with the absolute time in the tooltip and datetime attribute. */
export function RelativeTime({ value }: { value: TimeInput }) {
  useSyncExternalStore(subscribe, () => tick, () => 0);
  const date = toDate(value);
  return <time dateTime={date.toISOString()} title={formatDateTime(date)} className="tabular" suppressHydrationWarning>{formatRelative(date)}</time>;
}
