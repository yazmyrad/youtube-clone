// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { Me } from "../hooks/useAuth";
import { UserMenu } from "./UserMenu";

const authApi = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock("../api/client", () => ({ authApi }));
const auth = vi.hoisted(() => ({ switchAccount: vi.fn(), logoutAll: vi.fn() }));
vi.mock("../hooks/useAuth", () => ({ ACCOUNTS_KEY: ["accounts"], useAuth: () => auth }));

const ALICE = {
  id: "a",
  username: "alice",
  display_name: "Alice",
  avatar_url: null,
} as unknown as Me;
const ACCOUNTS = [
  { id: "a", username: "alice", display_name: "Alice", avatar_url: null },
  { id: "b", username: "bob", display_name: "Bob", avatar_url: "/channel-images/b.webp" },
];

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  authApi.GET.mockResolvedValue({ data: { items: ACCOUNTS } });
  auth.switchAccount.mockResolvedValue(undefined);
  auth.logoutAll.mockResolvedValue(undefined);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

const onLogout = vi.fn(async () => {});

async function openAccounts() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () =>
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/watch?v=x"]}>
          <UserMenu user={ALICE} onLogout={onLogout} />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  );
  await act(async () => button("Account menu")!.click());
  await act(async () => text("Switch account")!.click());
  await vi.waitFor(() => expect(container.textContent).toContain("@bob"));
}

const button = (label: string) =>
  container.querySelector<HTMLButtonElement>(`button[aria-label='${label}']`);
const text = (label: string) =>
  [...container.querySelectorAll<HTMLElement>("button, a")].find((el) =>
    el.textContent?.includes(label),
  );

it("lists the browser's accounts with the one in use marked", async () => {
  await openAccounts();

  const rows = [...container.querySelectorAll("[aria-label='Signed-in accounts'] button")];
  expect(rows.map((row) => row.textContent)).toEqual([
    expect.stringContaining("Alice@alice"),
    expect.stringContaining("Bob@bob"),
  ]);
  expect(rows[0]!.getAttribute("aria-current")).toBe("true");
  expect(rows[1]!.getAttribute("aria-current")).toBeNull();
  expect(container.querySelector("img")?.getAttribute("src")).toBe("/channel-images/b.webp");
});

it("switches to the account picked and closes", async () => {
  await openAccounts();

  await act(async () => text("Bob")!.click());

  expect(auth.switchAccount).toHaveBeenCalledWith("b");
  expect(container.textContent).not.toContain("Accounts");
});

it("shows why a switch failed", async () => {
  auth.switchAccount.mockRejectedValue(new Error("That account is signed out."));
  await openAccounts();

  await act(async () => text("Bob")!.click());

  expect(container.querySelector("[role=alert]")?.textContent).toBe("That account is signed out.");
});

it("adds an account, coming back to the same page", async () => {
  await openAccounts();

  expect(text("Add account")!.getAttribute("href")).toBe(
    `/login?add=1&next=${encodeURIComponent("/watch?v=x")}`,
  );
});

it("signs out of all accounts", async () => {
  await openAccounts();

  await act(async () => text("Sign out of all accounts")!.click());

  expect(auth.logoutAll).toHaveBeenCalledOnce();
});

it("goes back to the main menu", async () => {
  await openAccounts();

  await act(async () => button("Back")!.click());

  expect(text("Switch account")).toBeDefined();
  expect(text("Sign out")).toBeDefined();
});
