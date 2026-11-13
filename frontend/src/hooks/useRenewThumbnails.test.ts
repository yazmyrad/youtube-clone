import { expect, it } from "vitest";

import { MIN_RENEW_AGE_MS, shouldRenew } from "./useRenewThumbnails";

const now = 1_000_000_000;
const query = (age: number, isFetching = false) => ({
  dataUpdatedAt: now - age,
  isFetching,
  refetch: () => {},
});

it("reloads a list whose URLs may have expired", () => {
  expect(shouldRenew(query(2 * 3600_000), now)).toBe(true);
});

it("does not loop on an image that is broken for another reason", () => {
  expect(shouldRenew(query(MIN_RENEW_AGE_MS - 1), now)).toBe(false);
});

it("does not start a second fetch while one is running", () => {
  expect(shouldRenew(query(2 * 3600_000, true), now)).toBe(false);
});
