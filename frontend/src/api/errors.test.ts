import { describe, expect, it } from "vitest";

import { errorMessage } from "./errors";

describe("errorMessage", () => {
  it("returns a plain detail", () => {
    expect(errorMessage({ detail: "Nope" })).toBe("Nope");
  });

  it("returns the first problem of a validation error", () => {
    expect(errorMessage({ detail: [{ loc: ["body"], msg: "Too short" }] })).toBe("Too short");
  });

  it.each([undefined, null, "text", {}, { detail: [] }, { detail: [{}] }, { detail: 3 }])(
    "falls back for %j",
    (body) => {
      expect(errorMessage(body, "Fallback")).toBe("Fallback");
    },
  );
});
