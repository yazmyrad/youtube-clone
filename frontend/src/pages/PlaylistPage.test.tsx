// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { PlaylistPage } from "./PlaylistPage";

const api = vi.hoisted(() => ({ GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() }));
vi.mock("../api/client", () => ({ api }));

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
  channel: { username: "carol", display_name: "Carol" },
});

const playlist = (items = [card("a", "First"), card("b", "Second")]) => ({
  id: "p1",
  title: "Rust picks",
  description: "Best of Rust",
  visibility: "unlisted",
  channel: { username: "ana", display_name: "Ana Codes" },
  video_count: items.length,
  thumbnail_url: items[0]?.thumbnail_url ?? null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  items,
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
  api.PUT.mockReset();
  api.DELETE.mockReset();
  auth.user = null;
});

function serve(body: object | null) {
  api.GET.mockResolvedValue(
    body
      ? { data: body, response: new Response() }
      : { error: { detail: "Playlist not found" }, response: new Response(null, { status: 404 }) },
  );
}

async function shows(text: string) {
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(container.textContent).toContain(text);
  });
}

async function render(path = "/playlist?list=p1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/playlist" element={<PlaylistPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

const button = (label: string) =>
  container.querySelector<HTMLButtonElement>(`[aria-label='${label}']`);
const hrefs = () => [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));

it("shows the playlist, its videos in order, and Play all", async () => {
  serve(playlist());

  await render();
  await shows("Second");

  expect(container.querySelector("h1")?.textContent).toBe("Rust picks");
  expect(container.textContent).toContain("Unlisted · 2 videos");
  expect(container.textContent).toContain("Best of Rust");
  const titles = [...container.querySelectorAll("h2")].map((h) => h.textContent);
  expect(titles).toEqual(["First", "Second"]);
  const playAll = [...container.querySelectorAll("a")].find((a) => a.textContent === "Play all");
  expect(playAll?.getAttribute("href")).toBe("/watch?v=a&list=p1");
  expect(hrefs()).toContain("/watch?v=b&list=p1");
  expect(api.GET).toHaveBeenCalledWith(
    "/api/playlists/{playlist_id}",
    expect.objectContaining({ params: { path: { playlist_id: "p1" } } }),
  );
});

it("gives others no owner tools", async () => {
  auth.user = { username: "bob" };
  serve(playlist());

  await render();
  await shows("Second");

  expect(button('Remove "First" from the playlist')).toBeNull();
  expect(container.textContent).not.toContain("Delete playlist");
});

it("lets the owner move a video down", async () => {
  auth.user = { username: "ana" };
  serve(playlist());
  api.PUT.mockResolvedValue({ data: playlist([card("b", "Second"), card("a", "First")]) });

  await render();
  await shows("Second");
  expect(button('Move "First" up')?.disabled).toBe(true);
  await act(async () => button('Move "First" down')!.click());
  await shows("Second");

  expect(api.PUT).toHaveBeenCalledWith("/api/playlists/{playlist_id}/items/order", {
    params: { path: { playlist_id: "p1" } },
    body: { video_ids: ["b", "a"] },
  });
  await vi.waitFor(() => {
    const titles = [...container.querySelectorAll("h2")].map((h) => h.textContent);
    expect(titles).toEqual(["Second", "First"]);
  });
});

it("lets the owner remove a video", async () => {
  auth.user = { username: "ana" };
  serve(playlist());
  api.DELETE.mockResolvedValue({ data: playlist([card("b", "Second")]) });

  await render();
  await shows("First");
  await act(async () => button('Remove "First" from the playlist')!.click());

  await vi.waitFor(() => expect(container.textContent).not.toContain("First"));
  expect(api.DELETE).toHaveBeenCalledWith("/api/playlists/{playlist_id}/items/{video_id}", {
    params: { path: { playlist_id: "p1", video_id: "a" } },
  });
});

it("has no Play all when empty", async () => {
  serve(playlist([]));

  await render();
  await shows("No videos in this playlist yet.");

  expect(container.textContent).not.toContain("Play all");
});

it("is a not-found page for a playlist the caller can't see", async () => {
  serve(null);

  await render();

  await shows("This page isn't available");
});
