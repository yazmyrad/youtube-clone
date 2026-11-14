// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { UP_NEXT, UpNext } from "./UpNext";

const get = vi.hoisted(() => vi.fn());
vi.mock("../api/client", () => ({ api: { GET: get } }));

const card = (id: string) => ({
  id,
  title: `Video ${id}`,
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
});

async function render(videoId: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <UpNext videoId={videoId} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

const titles = () => [...container.querySelectorAll("h3")].map((h) => h.textContent);

it("lists the latest videos but the one playing, up to a limit", async () => {
  const items = Array.from({ length: UP_NEXT + 5 }, (_, i) => card(String(i)));
  get.mockResolvedValue({ data: { items, next_cursor: null } });

  await render("0");
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(titles().length).toBeGreaterThan(0);
  });

  expect(titles()).toHaveLength(UP_NEXT);
  expect(titles()).not.toContain("Video 0");
  expect(titles()[0]).toBe("Video 1");
  expect(container.querySelector("a[href='/@ana']")).not.toBeNull();
});

it("shows nothing when there's nothing else", async () => {
  get.mockResolvedValue({ data: { items: [card("0")], next_cursor: null } });

  await render("0");
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(container.querySelector("[aria-busy]")).toBeNull();
  });

  expect(container.textContent).toBe("");
});
