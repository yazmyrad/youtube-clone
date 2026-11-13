// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AdminUsersPage } from "./AdminUsersPage";

const api = vi.hoisted(() => ({ GET: vi.fn(), PATCH: vi.fn() }));
vi.mock("../api/client", () => ({ api }));

const auth = vi.hoisted(() => ({ user: null as { username: string; role: string } | null }));
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: auth.user, isLoading: false, logout: async () => {} }),
}));

const person = (username: string, role = "user", is_active = true) => ({
  id: `id-${username}`,
  username,
  email: `${username}@example.com`,
  display_name: username.toUpperCase(),
  role,
  is_active,
  created_at: "2026-01-01T00:00:00Z",
});

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
  api.GET.mockReset();
  api.PATCH.mockReset();
  auth.user = null;
});

async function shows(text: string) {
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(container.textContent).toContain(text);
  });
}

async function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/admin/users"]}>
          <AdminUsersPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

const select = (username: string) =>
  container.querySelector<HTMLSelectElement>(`select[aria-label='Role of ${username}']`)!;
const buttonNamed = (text: string) =>
  [...container.querySelectorAll<HTMLButtonElement>("button")].filter(
    (b) => b.textContent?.trim() === text,
  );

it.each([null, "user", "moderator"])("is not found for %s", async (role) => {
  auth.user = role ? { username: "bob", role } : null;

  await render();

  await shows("This page isn't available");
  expect(api.GET).not.toHaveBeenCalled();
});

it("lists users, with the admin's own row locked", async () => {
  auth.user = { username: "root", role: "admin" };
  api.GET.mockResolvedValue({
    data: { items: [person("alice"), person("root", "admin")], next_cursor: null },
  });

  await render();
  await shows("alice@example.com");

  expect(select("alice").disabled).toBe(false);
  expect(select("root").disabled).toBe(true);
  expect(buttonNamed("Disable").map((b) => b.disabled)).toEqual([false, true]);
});

it("changes a role and disables an account", async () => {
  auth.user = { username: "root", role: "admin" };
  api.GET.mockResolvedValue({ data: { items: [person("alice")], next_cursor: null } });
  api.PATCH.mockResolvedValue({ data: person("alice", "moderator") });

  await render();
  await shows("alice@example.com");
  await act(async () => {
    select("alice").value = "moderator";
    select("alice").dispatchEvent(new Event("change", { bubbles: true }));
  });
  await vi.waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
  await vi.waitFor(() => expect(buttonNamed("Disable")[0]!.disabled).toBe(false));
  await act(async () => buttonNamed("Disable")[0]!.click());

  await vi.waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(2));
  expect(api.PATCH.mock.calls.map((call) => call[1])).toEqual([
    { params: { path: { user_id: "id-alice" } }, body: { role: "moderator" } },
    { params: { path: { user_id: "id-alice" } }, body: { is_active: false } },
  ]);
});

it("searches", async () => {
  auth.user = { username: "root", role: "admin" };
  api.GET.mockResolvedValue({ data: { items: [person("alice")], next_cursor: null } });

  await render();
  await shows("alice@example.com");
  const input = container.querySelector<HTMLInputElement>("input[type=search]")!;
  await act(async () => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setValue.call(input, " ali ");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => buttonNamed("Search")[0]!.click());

  await vi.waitFor(() =>
    expect(api.GET).toHaveBeenLastCalledWith(
      "/api/admin/users",
      expect.objectContaining({ params: { query: { q: "ali", cursor: undefined } } }),
    ),
  );
});
