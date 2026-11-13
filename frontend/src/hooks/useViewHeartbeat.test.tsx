// @vitest-environment jsdom
import { act, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { HEARTBEAT_MS } from "../api/views";
import { useViewHeartbeat } from "./useViewHeartbeat";

const post = vi.hoisted(() => vi.fn(async () => ({ data: {} })));
vi.mock("../api/client", () => ({ api: { POST: post } }));

let container: HTMLDivElement;
let root: Root;
let time = 0;
let paused = true;

function Player() {
  const ref = useRef<HTMLVideoElement>(null);
  useViewHeartbeat(ref, "v1");
  return <video ref={ref} />;
}

beforeEach(async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers();
  time = 0;
  paused = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<Player />));
  const video = container.querySelector("video")!;
  Object.defineProperty(video, "currentTime", { get: () => time });
  Object.defineProperty(video, "paused", { get: () => paused });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  post.mockClear();
  vi.useRealTimers();
});

const video = () => container.querySelector("video")!;

function play(seconds: number) {
  paused = false;
  for (let i = 0; i < seconds * 4; i++) {
    time += 0.25;
    video().dispatchEvent(new Event("timeupdate"));
  }
}

const sent = () =>
  post.mock.calls.map((call) => (call as unknown as [string, { body: unknown }])[1].body);

it("reports while playing, every interval", () => {
  play(12);
  vi.advanceTimersByTime(HEARTBEAT_MS);

  expect(sent()).toEqual([{ watched_seconds: 11, position_seconds: 12 }]);
  expect(post).toHaveBeenCalledWith("/api/videos/{video_id}/view", expect.anything());
});

it("reports on pause, but not twice for the same moment", () => {
  play(3);
  paused = true;
  video().dispatchEvent(new Event("pause"));
  vi.advanceTimersByTime(HEARTBEAT_MS);
  video().dispatchEvent(new Event("pause"));

  expect(sent()).toEqual([{ watched_seconds: 2, position_seconds: 3 }]);
});

it("reports when leaving the video", () => {
  play(5);

  act(() => root.unmount());
  root = createRoot(container);

  expect(sent()).toHaveLength(1);
});

it("says nothing about a video that never played", () => {
  vi.advanceTimersByTime(HEARTBEAT_MS * 3);
  act(() => root.unmount());
  root = createRoot(container);

  expect(post).not.toHaveBeenCalled();
});

it("slows down once the view is settled", () => {
  const tick = () => {
    play(10);
    vi.advanceTimersByTime(HEARTBEAT_MS);
  };
  for (let i = 0; i < 3; i++) tick(); // Up to 30 s: a report every 10 s.
  expect(sent()).toHaveLength(3);

  tick();
  tick(); // Settled: 10 and 20 s after the last report are too soon.
  expect(sent()).toHaveLength(3);
  tick();

  expect(sent()).toHaveLength(4);
});

it("keeps the place when leaving after only seeking", () => {
  time = 95;
  video().dispatchEvent(new Event("seeked"));

  act(() => root.unmount());
  root = createRoot(container);

  expect(sent()).toEqual([{ watched_seconds: 0, position_seconds: 95 }]);
});
