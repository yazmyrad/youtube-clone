import { expect, it } from "vitest";

import config from "../vite.config";

it("collects component tests too", () => {
  expect(config.test?.include).toEqual(["src/**/*.test.{ts,tsx}"]);
});
