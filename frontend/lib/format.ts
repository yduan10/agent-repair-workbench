/** UI-08: one place for every date, duration and number shown in the UI. */

const dateTime = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
});
const shortDateTime = new Intl.DateTimeFormat("zh-CN", {
  month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
});
const timeOnly = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const dateOnly = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" });
const relative = new Intl.RelativeTimeFormat("zh-CN", { numeric: "auto" });
const integer = new Intl.NumberFormat("zh-CN");

export type TimeInput = number | string | Date;

/** Accepts epoch seconds (API run records), epoch milliseconds, ISO strings or Dates. */
export function toDate(value: TimeInput): Date {
  if (value instanceof Date) return value;
  if (typeof value === "number") return new Date(value < 1e12 ? value * 1000 : value);
  return new Date(value);
}

export function formatDateTime(value: TimeInput) {
  return dateTime.format(toDate(value));
}
export function formatShortDateTime(value: TimeInput) {
  return shortDateTime.format(toDate(value));
}
export function formatTime(value: TimeInput) {
  return timeOnly.format(toDate(value));
}
export function formatDate(value: TimeInput) {
  return dateOnly.format(toDate(value));
}

export function formatRelative(value: TimeInput, now = Date.now()) {
  const seconds = Math.round((toDate(value).getTime() - now) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return "刚刚";
  if (abs < 3600) return relative.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return relative.format(Math.round(seconds / 3600), "hour");
  if (abs < 86400 * 7) return relative.format(Math.round(seconds / 86400), "day");
  return formatShortDateTime(value);
}

/** Duration between two instants, or a millisecond count. */
export function formatDuration(ms: number | null | undefined) {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return "—";
  if (Math.round(ms) < 1000) return `${Math.round(ms)} 毫秒`;
  // Round once at the displayed precision, then split, so no unit ever shows its own carry
  // (59.6 s is "1 分钟", not "60 秒"; 119.6 s is "2 分钟", not "1 分 60 秒"; 9.96 s is "10 秒", not "10.0 秒").
  const tenths = Math.round(ms / 100);
  if (tenths < 100) return `${(tenths / 10).toFixed(1)} 秒`;
  const total = Math.round(ms / 1000);
  if (total < 60) return `${total} 秒`;
  if (total < 3600) {
    const m = Math.floor(total / 60), rest = total % 60;
    return rest ? `${m} 分 ${rest} 秒` : `${m} 分钟`;
  }
  const minutes = Math.round(total / 60);
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
}
export function durationBetween(start: TimeInput, end: TimeInput | null | undefined) {
  if (end === null || end === undefined) return null;
  return toDate(end).getTime() - toDate(start).getTime();
}

export function formatNumber(value: number) {
  return integer.format(value);
}
export function formatBytes(value: number) {
  if (value < 1024) return `${value} 字节`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
export function shortId(value: string, length = 8) {
  return value.replace(/^sha256:/, "").slice(0, length);
}
