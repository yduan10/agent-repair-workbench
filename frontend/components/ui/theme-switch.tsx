"use client";
import { useSyncExternalStore } from "react";
import { Monitor, Moon, Sun } from "lucide-react";

type Theme = "light" | "dark" | "system";
const KEY = "awb-theme";
const valid = (value: string | null | undefined): Theme => value === "light" || value === "dark" ? value : "system";

function apply(theme: Theme) {
  const root = document.documentElement;
  root.dataset.themePreference = theme;
  root.dataset.theme = theme === "system" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : theme;
}
function subscribe(callback: () => void) {
  const media = matchMedia("(prefers-color-scheme: dark)");
  const changed = () => { apply(valid(document.documentElement.dataset.themePreference)); callback(); };
  const storage = (event: StorageEvent) => { if (event.key === KEY || event.key === null) { apply(valid(event.newValue)); callback(); } };
  media.addEventListener("change", changed);
  window.addEventListener("awb-theme-change", changed);
  window.addEventListener("storage", storage);
  return () => { media.removeEventListener("change", changed); window.removeEventListener("awb-theme-change", changed); window.removeEventListener("storage", storage); };
}
const options: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "浅色", icon: Sun },
  { value: "dark", label: "深色", icon: Moon },
  { value: "system", label: "跟随系统", icon: Monitor },
];

export default function ThemeSwitch() {
  const theme = useSyncExternalStore(subscribe, () => valid(document.documentElement.dataset.themePreference), () => "system" as Theme);
  const choose = (choice: Theme) => {
    apply(choice);
    try { localStorage.setItem(KEY, choice); } catch { /* session only */ }
    window.dispatchEvent(new Event("awb-theme-change"));
  };
  return <div className="theme-switch" role="group" aria-label="外观主题">
    {options.map(({ value, label, icon: Icon }) => <button key={value} type="button" aria-pressed={theme === value} aria-label={label} title={label} onClick={() => choose(value)}>
      <Icon size={13} aria-hidden="true" />
    </button>)}
  </div>;
}
