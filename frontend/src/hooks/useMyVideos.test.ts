import { describe, expect, it } from "vitest";

import type { OwnerVideo } from "../api/upload";
import { needsPolling } from "./useMyVideos";

const page = (...statuses: OwnerVideo["status"][]) => ({
  items: statuses.map((status) => ({ status }) as OwnerVideo),
});

describe("needsPolling", () => {
  it("is off before the first answer", () => {
    expect(needsPolling(undefined)).toBe(false);
  });

  it("is on while a video on any page is processing", () => {
    expect(needsPolling([page("ready"), page("failed", "processing")])).toBe(true);
  });

  it("is off when nothing can change by itself", () => {
    expect(needsPolling([page("ready", "failed", "uploading")])).toBe(false);
  });
});
