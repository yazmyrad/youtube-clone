// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { SaveButton } from "./SaveButton";

const api = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), DELETE: vi.fn() }));
vi.mock("../api/client", () => ({ api }));

const auth = vi.hoisted(() => ({ user: null as { username: string } | null }));
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: auth.user, isLoading: false, logout: async () => {} }),
}));

const own = (id: string, title: string, contains_video: boolean) => ({
  id,
  title,
  visibility: "private",
  channel: { username: "ana", display_name: "Ana" },
  video_count: 0,
  thumbnail_url: null,
  updated_at: "2026-01-01T00:00:00Z",
  contains_video,
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
  api.POST.mockReset();
  api.DELETE.mockReset();
  auth.user = null;
});

function Where() {
  const { pathname, search } = useLocation();
  return <output data-testid="where">{pathname + search}</output>;
}

async function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/watch?v=v1"]}>
          <Routes>
            <Route path="*" element={<SaveButton videoId="v1" />} />
          </Routes>
          <Where />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

async function settle(check: () => void) {
  await vi.waitFor(async () => {
    await act(async () => {});
    check();
  });
}

const buttonNamed = (text: string) =>
  [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === text);
const boxes = () => [...container.querySelectorAll<HTMLInputElement>("input[type=checkbox]")];

it("sends a signed-out visitor to log in, and back", async () => {
  await render();

  await act(async () => buttonNamed("Save")!.click());

  expect(container.querySelector("[data-testid=where]")?.textContent).toBe(
    `/login?next=${encodeURIComponent("/watch?v=v1")}`,
  );
  expect(api.GET).not.toHaveBeenCalled();
});

it("lists the caller's playlists, ticking those that hold the video", async () => {
  auth.user = { username: "ana" };
  api.GET.mockResolvedValue({
    data: { items: [own("p1", "Rust", true), own("p2", "Go", false)], next_cursor: null },
  });

  await render();
  await act(async () => buttonNamed("Save")!.click());
  await settle(() => expect(boxes()).toHaveLength(2));

  expect(container.querySelector("[role=dialog]")?.textContent).toContain("Save video to...");
  expect(boxes().map((box) => box.checked)).toEqual([true, false]);
  expect(api.GET).toHaveBeenCalledWith(
    "/api/users/me/playlists",
    expect.objectContaining({ params: { query: { video_id: "v1", limit: 100 } } }),
  );
});

it("adds to a playlist when ticked, and removes when unticked", async () => {
  auth.user = { username: "ana" };
  api.GET.mockResolvedValue({
    data: { items: [own("p1", "Rust", true), own("p2", "Go", false)], next_cursor: null },
  });
  api.POST.mockResolvedValue({ data: { id: "p2", items: [] } });
  api.DELETE.mockResolvedValue({ data: { id: "p1", items: [] } });

  await render();
  await act(async () => buttonNamed("Save")!.click());
  await settle(() => expect(boxes()).toHaveLength(2));
  await act(async () => boxes()[1]!.click());
  await settle(() => expect(api.POST).toHaveBeenCalled());
  await settle(() => expect(boxes()[0]!.disabled).toBe(false));
  await act(async () => boxes()[0]!.click());
  await settle(() => expect(api.DELETE).toHaveBeenCalled());

  expect(api.POST).toHaveBeenCalledWith("/api/playlists/{playlist_id}/items", {
    params: { path: { playlist_id: "p2" } },
    body: { video_id: "v1" },
  });
  expect(api.DELETE).toHaveBeenCalledWith("/api/playlists/{playlist_id}/items/{video_id}", {
    params: { path: { playlist_id: "p1", video_id: "v1" } },
  });
});

it("creates a playlist with the video in it, and closes", async () => {
  auth.user = { username: "ana" };
  api.GET.mockResolvedValue({ data: { items: [], next_cursor: null } });
  api.POST.mockImplementation(async (path: string) =>
    path === "/api/playlists" ? { data: { id: "new" } } : { data: { id: "new", items: [] } },
  );

  await render();
  await act(async () => buttonNamed("Save")!.click());
  await act(async () => buttonNamed("Create new playlist")!.click());
  const input = container.querySelector<HTMLInputElement>("input:not([type])")!;
  await act(async () => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setValue.call(input, "  Later  ");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => buttonNamed("Create")!.click());
  await settle(() => expect(container.querySelector("[role=dialog]")).toBeNull());

  expect(api.POST).toHaveBeenCalledWith("/api/playlists", {
    body: { title: "Later", visibility: "private", description: "" },
  });
  expect(api.POST).toHaveBeenCalledWith("/api/playlists/{playlist_id}/items", {
    params: { path: { playlist_id: "new" } },
    body: { video_id: "v1" },
  });
});

it("closes on Escape", async () => {
  auth.user = { username: "ana" };
  api.GET.mockResolvedValue({ data: { items: [], next_cursor: null } });

  await render();
  await act(async () => buttonNamed("Save")!.click());
  expect(container.querySelector("[role=dialog]")).not.toBeNull();
  await act(async () => {
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  });

  expect(container.querySelector("[role=dialog]")).toBeNull();
});
