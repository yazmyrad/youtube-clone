// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { COLLAPSED_CHANNELS, FullGuide } from "./Guide";

const get = vi.hoisted(() => vi.fn());
vi.mock("../api/client", () => ({ api: { GET: get } }));

const auth = vi.hoisted(() => ({ user: null as { username: string } | null }));
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: auth.user, isLoading: false, logout: async () => {} }),
}));

const channels = (count: number) =>
  Array.from({ length: count }, (_, i) => ({
    username: `chan${i}`,
    display_name: `Channel ${i}`,
    subscribed_at: "2026-01-01T00:00:00Z",
  }));

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
  get.mockReset();
  auth.user = null;
});

async function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <FullGuide />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
  await act(async () => {});
}

const links = () => [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));

it("links Home and Subscriptions, and lists no channels when signed out", async () => {
  await render();

  expect(links()).toEqual(["/", "/feed/subscriptions"]);
  expect(get).not.toHaveBeenCalled();
});

it("lists the subscribed channels, and the rest after Show more", async () => {
  auth.user = { username: "bob" };
  get.mockResolvedValue({ data: { items: channels(COLLAPSED_CHANNELS + 2), next_cursor: null } });

  await render();

  await vi.waitFor(async () => {
    await act(async () => {});
    expect(links()).toHaveLength(2 + COLLAPSED_CHANNELS);
  });
  expect(links()).toContain("/@chan0");
  const more = [...container.querySelectorAll("button")].find(
    (b) => b.textContent === "Show 2 more",
  );
  await act(async () => more!.click());
  expect(links()).toHaveLength(2 + COLLAPSED_CHANNELS + 2);
  expect(container.textContent).toContain("Show fewer");
});

it("has no Subscriptions section without subscriptions", async () => {
  auth.user = { username: "bob" };
  get.mockResolvedValue({ data: { items: [], next_cursor: null } });

  await render();

  await vi.waitFor(() => expect(get).toHaveBeenCalled());
  await act(async () => {});
  expect(container.querySelector("section")).toBeNull();
});
