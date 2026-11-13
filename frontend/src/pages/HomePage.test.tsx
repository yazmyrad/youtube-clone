// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { HomePage } from "./HomePage";

const get = vi.hoisted(() => vi.fn());
vi.mock("../api/client", () => ({ api: { GET: get } }));

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
});

/** Waits until the page shows `text`, letting the query settle in between. */
async function shows(text: string) {
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(container.textContent).toContain(text);
  });
}

async function render() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <HomePage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

it("shows the feed, and the next page after Show more", async () => {
  get.mockResolvedValueOnce({
    data: { items: [card("a", "First")], next_cursor: "c1" },
  });
  get.mockResolvedValueOnce({
    data: { items: [card("b", "Second")], next_cursor: null },
  });

  await render();
  await shows("First");
  expect(get).toHaveBeenLastCalledWith(
    "/api/videos",
    expect.objectContaining({
      params: { query: { cursor: undefined } },
    }),
  );

  const more = [...container.querySelectorAll("button")].find((b) => b.textContent === "Show more");
  await act(async () => more!.click());

  await shows("Second");
  expect(get).toHaveBeenLastCalledWith(
    "/api/videos",
    expect.objectContaining({
      params: { query: { cursor: "c1" } },
    }),
  );
  expect(container.textContent).not.toContain("Show more");
});

it("says so when there are no videos", async () => {
  get.mockResolvedValueOnce({ data: { items: [], next_cursor: null } });

  await render();

  await shows("No videos yet");
});

it("offers a retry when the feed fails", async () => {
  get.mockResolvedValueOnce({ data: undefined, error: { detail: "boom" } });

  await render();

  await shows("Couldn't load videos");
  expect(container.querySelector('[role="alert"]')).not.toBeNull();
});
