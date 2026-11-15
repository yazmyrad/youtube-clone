// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it } from "vitest";

import { Avatar } from "./Avatar";

it("falls back to the letter when the picture won't load", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => root.render(<Avatar name="Ana" username="ana" src="/broken.webp" />));

  await act(async () => {
    container.querySelector("img")!.dispatchEvent(new Event("error"));
  });

  expect(container.querySelector("img")).toBeNull();
  expect(container.textContent).toBe("A");
  act(() => root.unmount());
});
