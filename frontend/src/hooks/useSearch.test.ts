import { expect, it } from "vitest";

import { searchText } from "./useSearch";

it.each([
  [null, null],
  ["", null],
  ["  a  ", null],
  ["ab", "ab"],
  ["  cats  ", "cats"],
  ["x".repeat(100), "x".repeat(100)],
  ["x".repeat(101), null],
])("searchText(%j) is %j, as the API would take it", (raw, expected) => {
  expect(searchText(raw)).toBe(expected);
});
