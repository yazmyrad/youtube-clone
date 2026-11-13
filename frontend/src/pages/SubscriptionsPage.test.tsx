// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { SubscriptionsPage } from "./SubscriptionsPage";

const get = vi.hoisted(() => vi.fn());
vi.mock("../api/client", () => ({ api: { GET: get } }));

const auth = vi.hoisted(() => ({ user: null as { username: string } | null }));
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: auth.user, isLoading: false, logout: async () => {} }),
}));

const card = (id: string, title: string) => ({
  id,
  title,
  duration_seconds: 61,
  views_count: 3,
  published_at: "2026-01-02T03:04:05Z",
  thumbnail_url: `/thumbs/${id}.jpg`,
  channel: { username: "ana", display_name: "Ana" },
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
  get.mockReset();
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
        <MemoryRouter initialEntries={["/feed/subscriptions"]}>
          <SubscriptionsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

it("asks a signed-out visitor to sign in, and loads nothing", async () => {
  await render();

  await shows("Don't miss new videos");
  expect(container.querySelector("a")?.getAttribute("href")).toBe(
    `/login?next=${encodeURIComponent("/feed/subscriptions")}`,
  );
  expect(get).not.toHaveBeenCalled();
});

it("shows the latest videos from subscriptions", async () => {
  auth.user = { username: "bob" };
  get.mockResolvedValue({
    data: { items: [card("a", "Git rebase explained")], next_cursor: null },
  });

  await render();

  await shows("Git rebase explained");
  expect(container.textContent).toContain("Latest");
  expect(get).toHaveBeenCalledWith(
    "/api/feed/subscriptions",
    expect.objectContaining({ params: { query: { cursor: undefined } } }),
  );
});

it("says what to do when there is nothing yet", async () => {
  auth.user = { username: "bob" };
  get.mockResolvedValue({ data: { items: [], next_cursor: null } });

  await render();

  await shows("No videos from your subscriptions yet");
});
