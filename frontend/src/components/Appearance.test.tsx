// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it } from "vitest";

import { setTheme, THEME_KEY, useDarkTheme } from "../theme";
import { SiteSettings } from "./SiteSettings";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  act(() => setTheme("device"));
});

const find = (label: string) =>
  [...container.querySelectorAll<HTMLElement>("button")].find((el) =>
    el.textContent?.includes(label),
  );
const checked = () =>
  [...container.querySelectorAll("[role=radio][aria-checked=true]")].map((el) => el.textContent);

async function openAppearance() {
  act(() => root.render(<SiteSettings />));
  act(() => container.querySelector<HTMLButtonElement>("[aria-label=Settings]")!.click());
  expect(find("Appearance: Device theme")).toBeDefined();
  act(() => find("Appearance:")!.click());
}

it("offers the device's theme, dark and light, with the one in use checked", async () => {
  await openAppearance();

  expect(container.textContent).toContain("Setting applies to this browser only");
  const options = [...container.querySelectorAll("[role=radio]")].map((el) => el.textContent);
  expect(options).toEqual(["Use device theme", "Dark theme", "Light theme"]);
  expect(checked()).toEqual(["Use device theme"]);
});

it("switches the page's theme and shows it in the menu", async () => {
  await openAppearance();

  act(() => find("Dark theme")!.click());

  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem(THEME_KEY)).toBe("dark");
  expect(checked()).toEqual(["Dark theme"]);
  act(() => container.querySelector<HTMLButtonElement>("[aria-label=Back]")!.click());
  expect(find("Appearance: Dark")).toBeDefined();
});

it("follows a theme picked in another tab", async () => {
  await openAppearance();

  act(() => {
    localStorage.setItem(THEME_KEY, "light");
    window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "light" }));
  });

  expect(document.documentElement.dataset.theme).toBe("light");
  expect(checked()).toEqual(["Light theme"]);
});

it("tells whether the page is dark: the choice, or else the device's", () => {
  let device = false;
  window.matchMedia = ((query: string) => ({
    matches: device && query.includes("dark"),
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
  const seen: boolean[] = [];
  function Probe() {
    seen.push(useDarkTheme());
    return null;
  }
  act(() => root.render(<Probe />));
  expect(seen.at(-1)).toBe(false);

  act(() => setTheme("dark"));
  expect(seen.at(-1)).toBe(true);

  device = true;
  act(() => setTheme("light"));
  expect(seen.at(-1)).toBe(false);

  act(() => setTheme("device"));
  expect(seen.at(-1)).toBe(true);
});

it("moves through the options with the arrow keys, as radio buttons do", async () => {
  await openAppearance();
  const current = () => container.querySelector<HTMLElement>("[role=radio][tabindex='0']")!;
  expect(current().textContent).toBe("Use device theme");
  current().focus();

  act(() => {
    current().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
  });

  expect(checked()).toEqual(["Dark theme"]);
  expect(document.activeElement?.textContent).toBe("Dark theme");
  act(() => {
    current().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }));
  });
  act(() => {
    current().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }));
  });
  expect(checked()).toEqual(["Light theme"]);
});
