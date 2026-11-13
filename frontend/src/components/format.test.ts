import { describe, expect, it } from "vitest";

import { formatAge, formatDuration, formatViews } from "./format";

describe("formatDuration", () => {
  it.each([
    [0, "0:00"],
    [5, "0:05"],
    [245, "4:05"],
    [3600, "1:00:00"],
    [3725.9, "1:02:05"],
  ])("%s s is %s", (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });
});

describe("formatViews", () => {
  it.each([
    [0, "0 views"],
    [1, "1 view"],
    [999, "999 views"],
    [1234, "1.2K views"],
    [2_500_000, "2.5M views"],
  ])("%s is %s", (count, expected) => {
    expect(formatViews(count)).toBe(expected);
  });
});

describe("formatAge", () => {
  const now = new Date("2026-06-15T12:00:00Z");

  it.each([
    ["2026-06-15T11:59:30Z", "just now"],
    ["2026-06-15T11:55:00Z", "5 minutes ago"],
    ["2026-06-15T10:00:00Z", "2 hours ago"],
    ["2026-06-12T12:00:00Z", "3 days ago"],
    ["2026-06-01T12:00:00Z", "2 weeks ago"],
    ["2025-06-15T12:00:00Z", "1 year ago"],
  ])("%s is %s", (iso, expected) => {
    expect(formatAge(iso, now)).toBe(expected);
  });

  it("does not go negative when the viewer's clock is behind", () => {
    expect(formatAge("2026-06-15T12:05:00Z", now)).toBe("just now");
  });
});
