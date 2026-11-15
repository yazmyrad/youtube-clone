// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { LoginPage } from "./LoginPage";

const auth = vi.hoisted(() => ({
  user: null as { id: string } | null,
  isLoading: false,
  login: vi.fn(),
  switchAccount: vi.fn(),
}));
vi.mock("../hooks/useAuth", () => ({ ACCOUNTS_KEY: ["accounts"], useAuth: () => auth }));
const authApi = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock("../api/client", () => ({ authApi }));

let container: HTMLDivElement;
let root: Root;

let client: QueryClient;

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  authApi.GET.mockResolvedValue({ data: { items: [] } });
  auth.switchAccount.mockResolvedValue(undefined);
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
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<p>home</p>} />
            <Route path="/watch" element={<p>watch</p>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
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

it("offers the accounts still signed in, never picking one itself", async () => {
  authApi.GET.mockResolvedValue({
    data: { items: [{ id: "b", username: "bob", display_name: "Bob", avatar_url: null }] },
  });

  await render("/login");
  await vi.waitFor(() => expect(container.textContent).toContain("Choose an account"));
  expect(auth.switchAccount).not.toHaveBeenCalled();

  const bob = [...container.querySelectorAll("button")].find((b) =>
    b.textContent?.includes("@bob"),
  )!;
  await act(async () => bob.click());

  expect(auth.switchAccount).toHaveBeenCalledWith("b");
});

it("shows only the form when no other account is signed in", async () => {
  await render("/login");
  await act(async () => {});

  expect(container.textContent).not.toContain("Choose an account");
  expect(container.querySelector("input[name=email]")).not.toBeNull();
});
