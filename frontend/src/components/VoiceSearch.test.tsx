// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { VoiceSearch } from "./VoiceSearch";

class FakeRecognition {
  static instances: FakeRecognition[] = [];
  lang = "";
  interimResults = false;
  continuous = true;
  maxAlternatives = 0;
  onresult: ((event: unknown) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn();
  abort = vi.fn(() => {
    this.onerror?.({ error: "aborted" });
    this.onend?.();
  });

  constructor() {
    FakeRecognition.instances.push(this);
  }

  hear(transcript: string, isFinal = false) {
    this.onresult?.({ results: [{ isFinal, 0: { transcript } }] });
  }
}

let container: HTMLDivElement;
let root: Root;
const onResult = vi.fn();

beforeEach(() => {
  Reflect.set(globalThis, "IS_REACT_ACT_ENVIRONMENT", true);
  FakeRecognition.instances = [];
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const button = (label: string) =>
  container.querySelector<HTMLButtonElement>(`button[aria-label='${label}']`);
const dialog = () => container.querySelector("[role=dialog]");
const listener = () => FakeRecognition.instances.at(-1)!;

function open() {
  act(() => root.render(<VoiceSearch onResult={onResult} />));
  act(() => button("Search with your voice")!.click());
}

it("listens, shows what it hears, and searches for it", () => {
  open();

  expect(dialog()?.getAttribute("aria-label")).toBe("Search with your voice");
  expect(dialog()!.textContent).toContain("Listening...");
  expect(listener().start).toHaveBeenCalledTimes(1);
  expect(listener().interimResults).toBe(true);
  expect(listener().continuous).toBe(false);

  act(() => listener().hear("big buck"));
  expect(dialog()!.textContent).toContain("big buck");
  expect(onResult).not.toHaveBeenCalled();

  act(() => listener().hear("big buck bunny ", true));
  expect(onResult).toHaveBeenCalledWith("big buck bunny");
  expect(dialog()).toBeNull();
});

it("says so when it heard nothing, and listens again from the microphone", () => {
  open();

  act(() => listener().onend?.());
  expect(dialog()!.textContent).toContain("Didn't hear that. Try again.");
  expect(dialog()!.textContent).toContain("Tap the microphone to try again");

  act(() => button("Try again")!.click());
  // Clicks while it listens do nothing, and the button keeps focus.
  expect(button("Listening")!.getAttribute("aria-disabled")).toBe("true");
  act(() => button("Listening")!.click());
  expect(FakeRecognition.instances).toHaveLength(2);
  expect(listener().start).toHaveBeenCalledTimes(1);
  expect(dialog()!.textContent).toContain("Listening...");
});

it("explains a blocked microphone", () => {
  open();

  act(() => listener().onerror?.({ error: "not-allowed" }));
  act(() => listener().onend?.());

  expect(dialog()!.textContent).toContain("Permission to use the microphone is blocked");
});

it("stops listening when cancelled", () => {
  open();
  const first = listener();

  act(() => button("Cancel")!.click());

  expect(dialog()).toBeNull();
  expect(first.abort).toHaveBeenCalled();
  expect(onResult).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(button("Search with your voice"));
});

it("closes on Escape", () => {
  open();

  act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));

  expect(dialog()).toBeNull();
});

it("offers no microphone where the browser can't recognize speech", () => {
  vi.stubGlobal("webkitSpeechRecognition", undefined);
  act(() => root.render(<VoiceSearch onResult={onResult} />));
  expect(button("Search with your voice")).toBeNull();
});

it("offers no microphone on a page that isn't secure", () => {
  vi.stubGlobal("isSecureContext", false);
  act(() => root.render(<VoiceSearch onResult={onResult} />));
  expect(button("Search with your voice")).toBeNull();
});

it("keeps Tab inside the dialog", () => {
  open();
  const cancel = button("Cancel")!;
  expect(document.activeElement).toBe(cancel);
  const tab = (shiftKey = false) =>
    act(() => {
      document.activeElement!.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Tab", shiftKey, bubbles: true }),
      );
    });

  tab();
  expect(document.activeElement).toBe(button("Listening"));
  tab();
  expect(document.activeElement).toBe(cancel);
  tab(true);
  expect(document.activeElement).toBe(button("Listening"));
});
