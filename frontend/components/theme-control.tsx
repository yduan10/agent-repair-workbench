"use client";

import { useSyncExternalStore } from "react";
import { Monitor, Moon, Sun } from "lucide-react";

type Theme = "light" | "dark" | "system";
const KEY = "awb-theme";
const valid = (value: string | null): Theme =>
  value === "light" || value === "dark" ? value : "system";

function apply(theme: Theme) {
  document.documentElement.dataset.themePreference = theme;
  document.documentElement.dataset.theme = theme === "system"
    ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
    : theme;
}
function subscribe(callback: () => void) {
  const media = matchMedia("(prefers-color-scheme: dark)");
  const changed = () => {
    apply(valid(document.documentElement.dataset.themePreference ?? null));
    callback();
  };
  const storage = (event: StorageEvent) => {
    if (event.key === KEY || event.key === null) {
      apply(valid(event.newValue));
      callback();
    }
  };
  media.addEventListener("change", changed);
  window.addEventListener("awb-theme-change", changed);
  window.addEventListener("storage", storage);
  return () => {
    media.removeEventListener("change", changed);
    window.removeEventListener("awb-theme-change", changed);
    window.removeEventListener("storage", storage);
  };
}

export default function ThemeControl() {
  const theme = useSyncExternalStore(subscribe,
    () => valid(document.documentElement.dataset.themePreference ?? null),
    () => "system" as Theme);
  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  const choose = (choice: Theme) => {
    apply(choice);
    try { localStorage.setItem(KEY, choice); } catch { /* Session-only when storage is blocked. */ }
    window.dispatchEvent(new Event("awb-theme-change"));
  };
  return <label className="theme-control">
    <Icon size={15} aria-hidden="true" />
    <span className="sr-only">外观主题</span>
    <select value={theme} onChange={event => choose(valid(event.target.value))}
      onKeyDown={event => {
        const choices: Theme[] = ["light", "dark", "system"];
        const index = choices.indexOf(theme);
        const next = event.key === "Home" ? 0 : event.key === "End" ? 2
          : event.key === "ArrowUp" ? Math.max(0, index - 1)
          : event.key === "ArrowDown" ? Math.min(2, index + 1) : null;
        if (next !== null) { event.preventDefault(); choose(choices[next]); }
      }}>
      <option value="light">浅色</option>
      <option value="dark">深色</option>
      <option value="system">跟随系统</option>
    </select>
  </label>;
}
