import { describe, expect, it, vi } from "vitest";

import { createApi } from "./client";
import { sendView, WatchTracker } from "./views";

describe("WatchTracker", () => {
  it("adds up steady playback", () => {
    const tracker = new WatchTracker();
    for (let t = 0; t <= 10; t += 0.25) tracker.update(t);

    expect(tracker.watched).toBeCloseTo(10);
  });

  it("doesn't count a jump ahead or back", () => {
    const tracker = new WatchTracker();
    tracker.update(0);
    tracker.update(0.5);
    tracker.update(60); // Skipped ahead.
    tracker.update(60.5);
    tracker.update(10); // Went back.

    expect(tracker.watched).toBeCloseTo(1);
  });

  it("starts afresh from where a seek lands", () => {
    const tracker = new WatchTracker();
    tracker.update(0);
    tracker.update(1);
    tracker.seeked(100);
    tracker.update(101);

    expect(tracker.watched).toBeCloseTo(2);
  });
});

it("sends whole seconds within the server's limits", async () => {
  const requests: Request[] = [];
  const fetchFn = vi.fn(async (request: Request) => {
    requests.push(request.clone());
    return Response.json({ counted: true, views_count: 1 });
  });

  await sendView(createApi("http://test", fetchFn), "v1", 30.7, 100_000);

  expect(requests[0]?.method).toBe("POST");
  expect(new URL(requests[0]?.url ?? "").pathname).toBe("/api/videos/v1/view");
  await expect(requests[0]?.json()).resolves.toEqual({
    watched_seconds: 30,
    position_seconds: 86_400,
  });
});
