// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { actionFor, isForPlayer, nextSpeed } from "./shortcuts";

const key = (k: string, extra: Partial<KeyboardEventInit> = {}) => ({
  key: k,
  shiftKey: false,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  ...extra,
});

describe("actionFor", () => {
  it.each([
    [" ", { kind: "toggle" }],
    ["k", { kind: "toggle" }],
    ["j", { kind: "seekBy", seconds: -10 }],
    ["l", { kind: "seekBy", seconds: 10 }],
    ["ArrowLeft", { kind: "seekBy", seconds: -5 }],
    ["ArrowRight", { kind: "seekBy", seconds: 5 }],
    ["ArrowUp", { kind: "volumeBy", delta: 0.05 }],
    ["ArrowDown", { kind: "volumeBy", delta: -0.05 }],
    ["m", { kind: "mute" }],
    ["f", { kind: "fullscreen" }],
    ["t", { kind: "theater" }],
    ["0", { kind: "seekToFraction", fraction: 0 }],
    ["7", { kind: "seekToFraction", fraction: 0.7 }],
    ["Home", { kind: "seekToFraction", fraction: 0 }],
    ["End", { kind: "seekToEnd" }],
    [",", { kind: "frame", direction: -1 }],
    [".", { kind: "frame", direction: 1 }],
    ["<", { kind: "speed", direction: -1 }],
    [">", { kind: "speed", direction: 1 }],
  ])("maps %j as YouTube does", (k, action) => {
    expect(actionFor(key(k))).toEqual(action);
  });

  it("needs SHIFT for next, and leaves browser shortcuts alone", () => {
    expect(actionFor(key("N", { shiftKey: true }))).toEqual({ kind: "next" });
    expect(actionFor(key("n"))).toBeNull();
    expect(actionFor(key("k", { ctrlKey: true }))).toBeNull();
    expect(actionFor(key("f", { metaKey: true }))).toBeNull();
    expect(actionFor(key("x"))).toBeNull();
  });
});

describe("isForPlayer", () => {
  it("ignores typing in a field and keys in a dialog", () => {
    const input = document.createElement("input");
    const dialog = document.createElement("div");
    dialog.setAttribute("aria-modal", "true");
    const inside = document.createElement("span");
    dialog.append(inside);

    expect(isForPlayer(input, "k")).toBe(false);
    expect(isForPlayer(inside, "k")).toBe(false);
    expect(isForPlayer(document.body, "k")).toBe(true);
  });

  it("lets space and Enter press a focused button", () => {
    const button = document.createElement("button");

    expect(isForPlayer(button, " ")).toBe(false);
    expect(isForPlayer(button, "Enter")).toBe(false);
    expect(isForPlayer(button, "k")).toBe(true);
  });
});

describe("nextSpeed", () => {
  it("steps through YouTube's speeds and stops at the ends", () => {
    expect(nextSpeed(1, 1)).toBe(1.25);
    expect(nextSpeed(1, -1)).toBe(0.75);
    expect(nextSpeed(2, 1)).toBe(2);
    expect(nextSpeed(0.25, -1)).toBe(0.25);
  });
});
