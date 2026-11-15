// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";

import { THEME_KEY } from "./theme";

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  vi.resetModules();
  vi.unstubAllGlobals();
});

// A fresh module each time, as on a page load.
const load = () => import("./theme");

it("pins the chosen theme on the root and remembers it", async () => {
  const { setTheme } = await load();

  setTheme("dark");
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem(THEME_KEY)).toBe("dark");

  setTheme("light");
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(localStorage.getItem(THEME_KEY)).toBe("light");
});

it("leaves the device to decide for the device theme", async () => {
  const { setTheme } = await load();
  setTheme("dark");

  setTheme("device");

  expect(document.documentElement.dataset.theme).toBeUndefined();
  expect(localStorage.getItem(THEME_KEY)).toBeNull();
});

it("still applies the theme when storage is blocked", async () => {
  const { setTheme } = await load();
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("blocked");
  });

  setTheme("dark");

  expect(document.documentElement.dataset.theme).toBe("dark");
  vi.restoreAllMocks();
});

it("applies the same rule as the script that runs before the first paint", async () => {
  const script = (await import("../public/theme.js?raw")).default;
  const run = (stored: string | null) => {
    delete document.documentElement.dataset.theme;
    if (stored === null) localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, stored);
    new Function(script)();
    return document.documentElement.dataset.theme;
  };

  expect(script).toContain(`"${THEME_KEY}"`);
  expect(run("dark")).toBe("dark");
  expect(run("light")).toBe("light");
  expect(run(null)).toBeUndefined();
  expect(run("<garbage>")).toBeUndefined();
});
