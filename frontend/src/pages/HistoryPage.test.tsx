// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { HistoryPage } from "./HistoryPage";

const api = vi.hoisted(() => ({ GET: vi.fn(), DELETE: vi.fn() }));
vi.mock("../api/client", () => ({ api }));

const auth = vi.hoisted(() => ({ user: null as { username: string } | null }));
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: auth.user, isLoading: false, logout: async () => {} }),
}));

const entry = (id: string, title: string, progress = 30) => ({
  video: {
    id,
    title,
    duration_seconds: 120,
    views_count: 3,
    published_at: "2026-01-02T03:04:05Z",
    thumbnail_url: `/thumbs/${id}.jpg`,
    channel: { username: "carol", display_name: "Carol" },
  },
  progress_seconds: progress,
  watched_at: "2026-01-03T00:00:00Z",
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
  api.DELETE.mockReset();
  auth.user = null;
  vi.restoreAllMocks();
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
        <MemoryRouter initialEntries={["/feed/history"]}>
          <HistoryPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

const buttonNamed = (text: string) =>
  [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === text);

it("asks a signed-out visitor to sign in, and loads nothing", async () => {
  await render();

  await shows("Keep track of what you watch");
  expect(api.GET).not.toHaveBeenCalled();
});

it("lists what was watched, with how far", async () => {
  auth.user = { username: "bob" };
  api.GET.mockResolvedValue({
    data: { items: [entry("a", "Rust in 100 Seconds"), entry("b", "tmux")], next_cursor: null },
  });

  await render();
  await shows("Rust in 100 Seconds");

  expect(container.textContent).toContain("tmux");
  const bar = container.querySelector<HTMLElement>("[data-testid=progress]");
  expect(bar?.style.width).toBe("25%");
});

it("removes one video", async () => {
  auth.user = { username: "bob" };
  api.GET.mockResolvedValue({ data: { items: [entry("a", "Rust")], next_cursor: null } });
  api.DELETE.mockResolvedValue({ response: new Response(null, { status: 204 }) });

  await render();
  await shows("Rust");
  await act(async () =>
    container
      .querySelector<HTMLButtonElement>("[aria-label='Remove \"Rust\" from watch history']")!
      .click(),
  );

  await vi.waitFor(() =>
    expect(api.DELETE).toHaveBeenCalledWith("/api/users/me/history/{video_id}", {
      params: { path: { video_id: "a" } },
    }),
  );
});

it("clears everything after asking", async () => {
  auth.user = { username: "bob" };
  api.GET.mockResolvedValue({ data: { items: [entry("a", "Rust")], next_cursor: null } });
  api.DELETE.mockResolvedValue({ response: new Response(null, { status: 204 }) });
  const confirm = vi.spyOn(window, "confirm");

  await render();
  await shows("Rust");
  confirm.mockReturnValueOnce(false);
  await act(async () => buttonNamed("Clear all watch history")!.click());
  expect(api.DELETE).not.toHaveBeenCalled();
  confirm.mockReturnValueOnce(true);
  await act(async () => buttonNamed("Clear all watch history")!.click());

  await vi.waitFor(() => expect(api.DELETE).toHaveBeenCalledWith("/api/users/me/history"));
});

it("says what will appear when empty", async () => {
  auth.user = { username: "bob" };
  api.GET.mockResolvedValue({ data: { items: [], next_cursor: null } });

  await render();

  await shows("Videos you watch will show up here.");
});
