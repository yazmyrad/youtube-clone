// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { SHELF_SIZE, ShortsShelf } from "./ShortsShelf";

const get = vi.hoisted(() => vi.fn());
vi.mock("../api/client", () => ({ api: { GET: get } }));

const short = (id: string) => ({
  id,
  title: `Short ${id}`,
  duration_seconds: 15,
  views_count: 1200,
  published_at: "2026-01-01T00:00:00Z",
  thumbnail_url: `/thumbs/${id}.jpg`,
  channel: { username: "wild_water", display_name: "Wild Water" },
  is_short: true,
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
});

async function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () =>
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ShortsShelf />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  );
}

it("shows the newest Shorts, each opening in the Shorts player", async () => {
  get.mockResolvedValue({
    data: { items: Array.from({ length: 9 }, (_, i) => short(String(i))), next_cursor: null },
  });

  await render();
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(container.querySelectorAll("article")).toHaveLength(SHELF_SIZE);
  });

  expect(get).toHaveBeenCalledWith("/api/videos/shorts", expect.anything());
  expect(container.querySelector("h2")?.textContent).toBe("Shorts");
  const links = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));
  expect(links).toContain("/shorts");
  expect(links).toContain("/shorts/0");
  expect(container.textContent).toContain("1.2K views");
});

it("isn't there without Shorts", async () => {
  get.mockResolvedValue({ data: { items: [], next_cursor: null } });

  await render();
  await vi.waitFor(() => expect(get).toHaveBeenCalled());
  await act(async () => {});

  expect(container.innerHTML).toBe("");
});
