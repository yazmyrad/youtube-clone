import { useSyncExternalStore } from "react";

/** YouTube's Appearance setting. It applies to this browser only, as on YouTube. */
export type Theme = "device" | "dark" | "light";

/** Also read by public/theme.js, which applies the theme before the first paint. */
export const THEME_KEY = "appearance.theme";

export const THEME_OPTIONS: readonly { value: Theme; label: string }[] = [
  { value: "device", label: "Use device theme" },
  { value: "dark", label: "Dark theme" },
  { value: "light", label: "Light theme" },
];

/** As in YouTube's menu row: "Appearance: Device theme". */
export const THEME_NAMES: Record<Theme, string> = {
  device: "Device theme",
  dark: "Dark",
  light: "Light",
};

const DARK_QUERY = "(prefers-color-scheme: dark)";

function parse(value: string | null): Theme {
  return value === "dark" || value === "light" ? value : "device";
}

function stored(): Theme {
  try {
    return parse(localStorage.getItem(THEME_KEY));
  } catch {
    // Storage blocked: the device decides.
    return "device";
  }
}

/** The root's data-theme pins a theme; without it, index.css follows the device. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "device") delete root.dataset.theme;
  else root.dataset.theme = theme;
}

let current: Theme | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());

function snapshot(): Theme {
  current ??= stored();
  return current;
}

export function setTheme(theme: Theme): void {
  current = theme;
  try {
    if (theme === "device") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Not remembered, then: it still applies until the page is closed.
  }
  applyTheme(theme);
  notify();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Another tab changed it: this one follows, as YouTube's tabs do.
  const onStorage = (event: StorageEvent) => {
    if (event.key !== THEME_KEY && event.key !== null) return;
    current = stored();
    applyTheme(current);
    notify();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, snapshot, () => "device");
}

function subscribeDevice(listener: () => void): () => void {
  const query = window.matchMedia?.(DARK_QUERY);
  query?.addEventListener("change", listener);
  return () => query?.removeEventListener("change", listener);
}

const deviceIsDark = () => window.matchMedia?.(DARK_QUERY).matches ?? false;

/** Whether the page is dark now: the chosen theme, or the device's for "device". */
export function useDarkTheme(): boolean {
  const theme = useTheme();
  const device = useSyncExternalStore(subscribeDevice, deviceIsDark, () => false);
  return theme === "dark" || (theme === "device" && device);
}
