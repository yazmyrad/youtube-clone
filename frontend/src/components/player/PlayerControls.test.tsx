// @vitest-environment jsdom
import { act, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { PlayerControls, qualityLabel, type Quality } from "./PlayerControls";
import { useMediaState } from "./useMediaState";

let container: HTMLDivElement;
let root: Root;
let element: HTMLVideoElement;
let paused = true;
const onTheater = vi.fn();
const onNext = vi.fn();
const select = vi.fn();

const QUALITY: Quality = { heights: [360, 720], selected: -1, playing: 720, select };

function Harness({ quality = QUALITY }: { quality?: Quality | null }) {
  const video = useRef<HTMLVideoElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const state = useMediaState(video);
  return (
    <div ref={box}>
      <video ref={video} />
      <PlayerControls
        video={video}
        container={box}
        state={state}
        quality={quality}
        theater={false}
        onTheater={onTheater}
        onNext={onNext}
      />
    </div>
  );
}

beforeEach(async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  paused = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  // jsdom has no media playback: stand in for the parts the controls use.
  const proto = HTMLMediaElement.prototype as unknown as Record<string, unknown>;
  Object.defineProperty(proto, "paused", { configurable: true, get: () => paused });
  Object.defineProperty(proto, "duration", { configurable: true, get: () => 100 });
  proto.play = vi.fn(function (this: HTMLMediaElement) {
    paused = false;
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  proto.pause = vi.fn(function (this: HTMLMediaElement) {
    paused = true;
    this.dispatchEvent(new Event("pause"));
  });
  await act(async () => root.render(<Harness />));
  element = container.querySelector("video")!;
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

const button = (label: string) =>
  container.querySelector<HTMLButtonElement>(`button[aria-label^='${label}']`);
const press = async (key: string, init: KeyboardEventInit = {}) =>
  act(async () => {
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, ...init }));
  });

it("plays and pauses from the button, the picture and the keyboard", async () => {
  await act(async () => button("Play (k)")!.click());
  expect(element.play).toHaveBeenCalledTimes(1);
  expect(button("Pause (k)")).not.toBeNull();

  await press("k");
  expect(element.pause).toHaveBeenCalledTimes(1);

  await press(" ");
  expect(element.play).toHaveBeenCalledTimes(2);
});

it("seeks like YouTube's keys", async () => {
  element.currentTime = 50;
  await press("l");
  expect(element.currentTime).toBe(60);
  await press("j");
  await press("j");
  expect(element.currentTime).toBe(40);
  await press("ArrowLeft");
  expect(element.currentTime).toBe(35);
  await press("7");
  expect(element.currentTime).toBe(70);
  await press("j");
  await press("0");
  expect(element.currentTime).toBe(0);
  await press("j");
  expect(element.currentTime).toBe(0);
});

it("changes volume and mutes, and remembers it", async () => {
  element.volume = 0.5;
  await press("ArrowUp");
  expect(element.volume).toBeCloseTo(0.55);
  await press("m");
  expect(element.muted).toBe(true);
  expect(button("Unmute (m)")).not.toBeNull();
  expect(JSON.parse(localStorage.getItem("player.volume")!)).toEqual({
    volume: 0.55,
    muted: true,
  });
});

it("changes speed from the keyboard and the settings menu", async () => {
  await press(">");
  expect(element.playbackRate).toBe(1.25);

  await act(async () => button("Settings")!.click());
  const rows = () => [...container.querySelectorAll<HTMLButtonElement>("[role^=menuitem]")];
  expect(rows().map((row) => row.textContent)).toEqual([
    "Playback speed1.25",
    "QualityAuto (720p)",
  ]);
  await act(async () => rows()[0]!.click());
  await act(async () =>
    rows()
      .find((row) => row.textContent === "1.5")!
      .click(),
  );

  expect(element.playbackRate).toBe(1.5);
  expect(container.querySelector("[role=menu]")).toBeNull();
});

it("picks a quality, highest first, with Auto last", async () => {
  await act(async () => button("Settings")!.click());
  const rows = () => [...container.querySelectorAll<HTMLButtonElement>("[role^=menuitem]")];
  await act(async () => rows()[1]!.click());

  expect(rows().map((row) => row.textContent)).toEqual(["720p", "360p", "Auto (720p)"]);
  expect(rows()[2]!.getAttribute("aria-checked")).toBe("true");
  await act(async () => rows()[1]!.click());
  expect(select).toHaveBeenCalledWith(0);
});

it("closes the menu on Escape", async () => {
  await act(async () => button("Settings")!.click());
  await press("Escape");

  expect(container.querySelector("[role=menu]")).toBeNull();
});

it("has Next and Theater, with their keys", async () => {
  await act(async () => button("Next")!.click());
  await press("N", { shiftKey: true });
  await press("t");
  await act(async () => button("Theater mode (t)")!.click());

  expect(onNext).toHaveBeenCalledTimes(2);
  expect(onTheater).toHaveBeenCalledTimes(2);
});

it("leaves keys typed into a field alone", async () => {
  const input = document.createElement("input");
  document.body.append(input);

  await act(async () => {
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "k", bubbles: true }));
  });

  expect(element.play).not.toHaveBeenCalled();
  input.remove();
});

it("shows the time played and the length", async () => {
  await act(async () => {
    element.currentTime = 75;
    element.dispatchEvent(new Event("timeupdate"));
  });

  expect(container.textContent).toContain("1:15 / 1:40");
  expect(container.querySelector("[aria-label=Seek]")?.getAttribute("aria-valuenow")).toBe("75");
});

it("labels Auto with what it plays", () => {
  expect(qualityLabel(null)).toBe("Auto");
  expect(qualityLabel({ ...QUALITY, playing: null })).toBe("Auto");
  expect(qualityLabel(QUALITY)).toBe("Auto (720p)");
  expect(qualityLabel({ ...QUALITY, selected: 0 })).toBe("360p");
});
