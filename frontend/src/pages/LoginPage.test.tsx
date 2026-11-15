// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { LoginPage } from "./LoginPage";

const auth = vi.hoisted(() => ({
  user: null as { id: string } | null,
  isLoading: false,
  login: vi.fn(),
}));
vi.mock("../hooks/useAuth", () => ({ useAuth: () => auth }));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  auth.user = null;
});

async function render(path: string) {
  await act(async () =>
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<p>home</p>} />
          <Route path="/watch" element={<p>watch</p>} />
        </Routes>
      </MemoryRouter>,
    ),
  );
}

it("sends someone already signed in on", async () => {
  auth.user = { id: "a" };

  await render("/login");

  expect(container.textContent).toBe("home");
});

it("lets someone signed in add another account, then moves on", async () => {
  auth.user = { id: "a" };

  await render(`/login?add=1&next=${encodeURIComponent("/watch?v=x")}`);
  expect(container.querySelector("h1")?.textContent).toBe("Add account");

  auth.user = { id: "b" }; // The new account is in.
  await render(`/login?add=1&next=${encodeURIComponent("/watch?v=x")}`);

  expect(container.textContent).toBe("watch");
});
