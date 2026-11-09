import { describe, expect, it } from "vitest";

import { safeNext } from "./safeNext";

describe("safeNext", () => {
  it.each(["/", "/watch?v=1", "/channel/ana#about"])("keeps the path %s", (next) => {
    expect(safeNext(next)).toBe(next);
  });

  it.each([
    null,
    "",
    "https://evil.test",
    "evil.test",
    "//evil.test",
    "/\\evil.test",
    "\\\\evil.test",
    "/\t/evil.test",
    "/\n/evil.test",
    "javascript:alert(1)",
  ])("sends %j home", (next) => {
    expect(safeNext(next)).toBe("/");
  });
});
