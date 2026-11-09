import { describe, expect, it } from "vitest";

import { statusMessage, videoKey } from "./useVideo";

describe("statusMessage", () => {
  it("says nothing for a video that can play", () => {
    expect(statusMessage("ready")).toBeNull();
  });

  it.each(["uploading", "processing", "failed"] as const)("explains %s", (status) => {
    expect(statusMessage(status)).toBeTruthy();
  });
});

describe("videoKey", () => {
  it("differs by account", () => {
    expect(videoKey("v1", "ana")).not.toEqual(videoKey("v1", null));
  });
});
