// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChannelPage, handleToUsername } from "./ChannelPage";

const api = vi.hoisted(() => ({ GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() }));
vi.mock("../api/client", () => ({ api }));

const auth = vi.hoisted(() => ({ user: null as { username: string } | null }));
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: auth.user, isLoading: false, logout: async () => {} }),
}));

const CHANNEL = {
  username: "ana",
  display_name: "Ana Codes",
  description: "Short videos about code",
  subscribers_count: 1234,
  created_at: "2026-01-01T00:00:00Z",
  is_subscribed: false,
};

const card = (id: string, title: string, visibility = "public") => ({
  id,
  title,
  duration_seconds: 61,
  views_count: 3,
  published_at: "2026-01-02T03:04:05Z",
  thumbnail_url: `/thumbs/${id}.jpg`,
  channel: { username: "ana", display_name: "Ana Codes" },
  visibility,
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

/** Answers the channel and its videos by path. */
function serve(channel: object | null, items: object[] = []) {
  api.GET.mockImplementation(async (path: string) => {
    if (path === "/api/channels/{username}") {
      return channel
        ? { data: channel, response: new Response() }
        : { error: { detail: "Channel not found" }, response: new Response(null, { status: 404 }) };
    }
    return { data: { items, next_cursor: null } };
  });
}

async function shows(text: string) {
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(container.textContent).toContain(text);
  });
}

function Where() {
  const { pathname, search } = useLocation();
  return <output data-testid="where">{pathname + search}</output>;
}

async function render(path = "/@ana") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/:handle" element={<ChannelPage />} />
          </Routes>
          <Where />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

/** Waits for the header button and for the video list to settle. */
async function ready(label: string) {
  await shows("This channel has no videos yet.");
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(button(label)).toBeDefined();
  });
}

function button(name: string) {
  return [...container.querySelectorAll("button")].find((b) => b.textContent === name);
}

describe("handleToUsername", () => {
  it.each([
    ["@ana", "ana"],
    ["ana", null],
    ["@", null],
    [undefined, null],
  ])("%s gives %s", (handle, username) => {
    expect(handleToUsername(handle)).toBe(username);
  });
});

it("shows the channel header and its videos", async () => {
  serve(CHANNEL, [card("a", "Rust in 100 Seconds")]);

  await render();
  await shows("Rust in 100 Seconds");

  expect(container.querySelector("h1")?.textContent).toBe("Ana Codes");
  expect(container.textContent).toContain("@ana");
  expect(container.textContent).toContain("1.2K subscribers");
  expect(container.textContent).toContain("Short videos about code");
  expect(api.GET).toHaveBeenCalledWith(
    "/api/channels/{username}/videos",
    expect.objectContaining({
      params: { path: { username: "ana" }, query: { cursor: undefined } },
    }),
  );
});

it("subscribes, and shows the new count", async () => {
  auth.user = { username: "bob" };
  serve(CHANNEL);
  api.PUT.mockResolvedValue({ data: { is_subscribed: true, subscribers_count: 1235 } });

  await render();
  await ready("Subscribe");
  await act(async () => button("Subscribe")!.click());
  await ready("Subscribed");

  expect(api.PUT).toHaveBeenCalledWith("/api/channels/{username}/subscription", {
    params: { path: { username: "ana" } },
  });
  expect(container.textContent).toContain("1.2K subscribers");
  expect(button("Subscribed")?.getAttribute("aria-pressed")).toBe("true");
});

it("unsubscribes", async () => {
  auth.user = { username: "bob" };
  serve({ ...CHANNEL, is_subscribed: true });
  api.DELETE.mockResolvedValue({ data: { is_subscribed: false, subscribers_count: 1233 } });

  await render();
  await ready("Subscribed");
  await act(async () => button("Subscribed")!.click());
  await ready("Subscribe");

  expect(api.DELETE).toHaveBeenCalled();
  expect(button("Subscribe")).toBeDefined();
});

it("sends a signed-out visitor to log in, and back", async () => {
  serve(CHANNEL);

  await render();
  await ready("Subscribe");
  await act(async () => button("Subscribe")!.click());

  expect(api.PUT).not.toHaveBeenCalled();
  expect(container.querySelector("[data-testid=where]")?.textContent).toBe(
    `/login?next=${encodeURIComponent("/@ana")}`,
  );
});

it("shows the owner Manage videos, not Subscribe, and labels their hidden-from-others videos", async () => {
  auth.user = { username: "ana" };
  serve(CHANNEL, [card("a", "Draft", "private"), card("b", "Link only", "unlisted")]);

  await render();
  await shows("Draft");

  expect(button("Subscribe")).toBeUndefined();
  expect(container.textContent).toContain("Manage videos");
  expect(container.textContent).toContain("Private");
  expect(container.textContent).toContain("Unlisted");
});

it("says so when the channel has no videos", async () => {
  serve(CHANNEL);

  await render();

  await shows("This channel has no videos yet.");
});

it("is a not-found page for an unknown channel", async () => {
  serve(null);

  await render("/@nobody");

  await shows("This page isn't available");
});
