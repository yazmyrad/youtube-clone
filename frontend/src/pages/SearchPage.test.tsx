// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Masthead } from "../components/Masthead";
import { SearchPage } from "./SearchPage";

const get = vi.hoisted(() => vi.fn());
vi.mock("../api/client", () => ({ api: { GET: get } }));
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: null, isLoading: false, logout: async () => {} }),
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
let location = "";

function Where() {
  const { pathname, search } = useLocation();
  location = pathname + search;
  return null;
}

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

async function render(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <Masthead onMenu={() => {}} />
          <Where />
          <Routes>
            <Route path="/" element={<p>Home</p>} />
            <Route path="/results" element={<SearchPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

async function shows(text: string) {
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(container.textContent).toContain(text);
  });
}

const input = () => container.querySelector<HTMLInputElement>('input[name="search_query"]')!;

async function search(text: string) {
  await act(async () => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setValue.call(input(), text);
    input().dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => {
    input().form!.requestSubmit();
  });
}

it("searches from the masthead and lists the results", async () => {
  get.mockResolvedValueOnce({ data: { items: [card("a", "Funny cats")], next_cursor: null } });
  await render("/");

  await search("  funny cats & 100%  ");

  expect(location).toBe("/results?search_query=funny%20cats%20%26%20100%25");
  await shows("Funny cats");
  expect(get).toHaveBeenCalledWith(
    "/api/search/videos",
    expect.objectContaining({ params: { query: { q: "funny cats & 100%", cursor: undefined } } }),
  );
  expect(input().value).toBe("funny cats & 100%");
});

it("does not leave the page for an empty search", async () => {
  await render("/");

  await search("   ");

  expect(location).toBe("/");
});

it("asks for more characters without calling the API", async () => {
  await render("/results?search_query=a");

  await shows("Type at least 2 characters");
  expect(get).not.toHaveBeenCalled();
});

it("says so when nothing matches", async () => {
  get.mockResolvedValueOnce({ data: { items: [], next_cursor: null } });
  await render("/results?search_query=zzz");

  await shows("No results found");
});

it("reports a failed search", async () => {
  get.mockResolvedValueOnce({ data: undefined, error: { detail: "boom" } });
  await render("/results?search_query=cats");

  await shows("Couldn't search right now");
  expect(container.querySelector('[role="alert"]')).not.toBeNull();
});
