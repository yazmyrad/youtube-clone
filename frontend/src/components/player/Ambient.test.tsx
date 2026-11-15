// @vitest-environment jsdom
import { act, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AMBIENT_KEY, AmbientGlow, useAmbientSetting } from "./Ambient";

let container: HTMLDivElement;
let root: Root;
let readyState = 0;
let paused = true;
const drawImage = vi.fn();
const context = { globalAlpha: 1, drawImage };
const alphas: number[] = [];
let frames: FrameRequestCallback[] = [];

beforeEach(() => {
  Reflect.set(globalThis, "IS_REACT_ACT_ENVIRONMENT", true);
  localStorage.clear();
  readyState = 0;
  paused = true;
  alphas.length = 0;
  frames = [];
  drawImage.mockImplementation(() => alphas.push(context.globalAlpha));
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    context as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(HTMLMediaElement.prototype, "readyState", "get").mockImplementation(() => readyState);
  vi.spyOn(HTMLMediaElement.prototype, "paused", "get").mockImplementation(() => paused);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.push(callback);
    return frames.length;
  });
  vi.stubGlobal("cancelAnimationFrame", () => {
    frames = [];
  });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function Glow() {
  const video = useRef<HTMLVideoElement>(null);
  return (
    <>
      <video ref={video} />
      <AmbientGlow video={video} />
    </>
  );
}

const video = () => container.querySelector("video")!;
const fire = (name: string) => act(() => void video().dispatchEvent(new Event(name)));
/** Runs the animation frames due at this time, as the browser would. */
const tick = (now: number) =>
  act(() => {
    const due = frames;
    frames = [];
    due.forEach((callback) => callback(now));
  });

it("draws nothing before the video has a frame, then shows the first one at once", () => {
  act(() => root.render(<Glow />));
  expect(drawImage).not.toHaveBeenCalled();
  const canvas = container.querySelector("canvas[data-ambient]")!;
  expect(canvas.getAttribute("aria-hidden")).toBe("true");

  readyState = 2;
  fire("loadeddata");

  expect(drawImage).toHaveBeenCalledWith(video(), 0, 0, 32, 18);
  expect(alphas).toEqual([1]);
});

it("blends toward the playing video a little at a time, and stops when it pauses", () => {
  readyState = 2;
  act(() => root.render(<Glow />));
  alphas.length = 0;

  paused = false;
  fire("playing");
  tick(50);
  tick(100);
  tick(150);
  tick(200);
  expect(alphas).toEqual([0.15, 0.15]);

  paused = true;
  fire("pause");
  expect(frames).toEqual([]);
  tick(400);
  expect(alphas).toHaveLength(2);
});

it("jumps to the new picture after a seek", () => {
  readyState = 2;
  act(() => root.render(<Glow />));
  alphas.length = 0;

  fire("seeked");

  expect(alphas).toEqual([1]);
});

it("stops drawing when it goes away", () => {
  readyState = 2;
  paused = false;
  act(() => root.render(<Glow />));
  expect(frames).toHaveLength(1);

  act(() => root.render(null));

  expect(frames).toEqual([]);
});

it("is on unless turned off, and remembers the choice", () => {
  const seen: boolean[] = [];
  let toggle = () => {};
  function Probe() {
    const [on, flip] = useAmbientSetting();
    seen.push(on);
    toggle = flip;
    return null;
  }
  act(() => root.render(<Probe />));
  expect(seen.at(-1)).toBe(true);

  act(() => toggle());
  expect(seen.at(-1)).toBe(false);
  expect(localStorage.getItem(AMBIENT_KEY)).toBe("0");

  act(() => root.render(null));
  act(() => root.render(<Probe />));
  expect(seen.at(-1)).toBe(false);
});
