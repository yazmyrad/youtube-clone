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
  avatar_url: null as string | null,
  banner_url: null as string | null,
  videos_count: 1,
  views_count: 1234567,
  created_at: "2026-01-01T12:00:00Z",
  is_subscribed: false,
};

const card = (id: string, title: string, visibility = "public") => ({
  id,
  title,
  duration_seconds: 61,
  views_count: 3,
  published_at: "2026-01-02T03:04:05Z",
  thumbnail_url: `/thumbs/${id}.jpg`,
  channel: { username: "ana", display_name: "Ana Codes", avatar_url: null },
  visibility,
  is_short: false,
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
            <Route path="/:handle/:tab?" element={<ChannelPage />} />
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

  await render("/@ana/videos");
  await shows("Rust in 100 Seconds");

  expect(container.querySelector("h1")?.textContent).toBe("Ana Codes");
  expect(container.textContent).toContain("@ana");
  expect(container.textContent).toContain("1.2K subscribers");
  expect(container.textContent).toContain("1 video");
  expect(container.textContent).toContain("Short videos about code");
  expect(api.GET).toHaveBeenCalledWith(
    "/api/channels/{username}/videos",
    expect.objectContaining({
      params: { path: { username: "ana" }, query: { cursor: undefined, sort: "latest" } },
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

  await render("/@ana/videos");
  await shows("Draft");

  expect(button("Subscribe")).toBeUndefined();
  expect(container.textContent).toContain("Manage videos");
  const links = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));
  expect(links).toContain("/customize");
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

it("lists the channel's playlists on its Playlists tab", async () => {
  api.GET.mockImplementation(async (path: string) => {
    if (path === "/api/channels/{username}") return { data: CHANNEL, response: new Response() };
    if (path === "/api/channels/{username}/playlists") {
      return {
        data: {
          items: [
            {
              id: "p1",
              title: "Rust picks",
              visibility: "public",
              channel: { username: "ana", display_name: "Ana Codes", avatar_url: null },
              video_count: 3,
              thumbnail_url: "/thumbs/a.jpg",
              updated_at: "2026-01-02T00:00:00Z",
            },
          ],
          next_cursor: null,
        },
      };
    }
    throw new Error(`unexpected ${path}`);
  });

  await render("/@ana/playlists");
  await shows("Rust picks");

  expect(container.textContent).toContain("3 videos");
  const links = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));
  expect(links).toContain("/playlist?list=p1");
  expect(links).toContain("/@ana/videos");
  const current = container.querySelector("nav [aria-current=page]");
  expect(current?.textContent).toBe("Playlists");
});

it("says so when the channel has no playlists", async () => {
  serve(CHANNEL);

  await render("/@ana/playlists");

  await shows("This channel has no playlists.");
});

it("is a not-found page for an unknown tab", async () => {
  serve(CHANNEL);

  await render("/@ana/about-us");

  await shows("This page isn't available");
});

/** Answers each list by its path and sort, for the Home tab's shelves. */
function serveLists(lists: Record<string, object[]>, channel: object = CHANNEL) {
  api.GET.mockImplementation(
    async (path: string, init: { params?: { query?: { sort?: string; q?: string } } }) => {
      if (path === "/api/channels/{username}") return { data: channel, response: new Response() };
      const sort = init.params?.query?.sort;
      const items = lists[sort ? `${path}?sort=${sort}` : path] ?? [];
      return { data: { items, next_cursor: null } };
    },
  );
}

function hrefs() {
  return [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));
}

it("opens on Home: the newest video, then shelves of videos, Shorts and the most viewed", async () => {
  const short = { ...card("s", "A quick tip"), is_short: true };
  serveLists({
    "/api/channels/{username}/videos?sort=latest": [
      card("a", "Newest one"),
      card("b", "Middle one"),
      card("c", "Oldest one"),
    ],
    "/api/channels/{username}/videos?sort=popular": [card("c", "Oldest one")],
    "/api/channels/{username}/shorts?sort=latest": [short],
  });

  await render();
  await shows("A quick tip");

  const featured = container.querySelector("[aria-label='Featured video']");
  expect(featured?.textContent).toContain("Newest one");
  const headings = [...container.querySelectorAll("h2")].map((h) => h.textContent);
  expect(headings).toEqual(expect.arrayContaining(["Videos", "Shorts", "Popular videos"]));
  expect(hrefs()).toEqual(
    expect.arrayContaining(["/@ana/videos", "/@ana/shorts", "/@ana/videos?sort=popular"]),
  );
  expect(container.querySelector("nav [aria-current=page]")?.textContent).toBe("Home");
});

it("sorts the Videos tab by the chip chosen, kept in the address", async () => {
  serveLists({
    "/api/channels/{username}/videos?sort=latest": [card("a", "Newest one")],
    "/api/channels/{username}/videos?sort=popular": [card("p", "Most watched")],
  });

  await render("/@ana/videos");
  await shows("Newest one");
  await act(async () => button("Popular")!.click());
  await shows("Most watched");

  expect(container.querySelector("[data-testid=where]")?.textContent).toBe(
    "/@ana/videos?sort=popular",
  );
  expect(button("Popular")?.getAttribute("aria-pressed")).toBe("true");
});

it("shows the banner and the channel's picture", async () => {
  serveLists(
    {},
    { ...CHANNEL, avatar_url: "/channel-images/a.webp", banner_url: "/channel-images/b.webp" },
  );

  await render();
  await shows("This channel has no videos yet.");

  const images = [...container.querySelectorAll("img")].map((img) => img.getAttribute("src"));
  expect(images).toEqual(
    expect.arrayContaining(["/channel-images/a.webp", "/channel-images/b.webp"]),
  );
});

it("opens About with the whole description and the channel's numbers, and closes on Escape", async () => {
  serveLists({});

  await render();
  await shows("...more");
  const more = [...container.querySelectorAll("button")].find((b) =>
    b.textContent?.includes("...more"),
  )!;
  more.focus(); // As a real click would.
  await act(async () => more.click());

  const dialog = container.querySelector("[role=dialog]");
  expect(dialog?.textContent).toContain("Short videos about code");
  expect(dialog?.textContent).toContain("1,234,567 views");
  expect(dialog?.textContent).toContain("1 video");
  expect(dialog?.textContent).toContain("Joined Jan 1, 2026");
  expect(document.activeElement).toBe(dialog);
  await act(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  });
  expect(container.querySelector("[role=dialog]")).toBeNull();
  expect(document.activeElement).toBe(more);
});

it("keeps Tab inside the About box", async () => {
  serveLists({});

  await render();
  await shows("...more");
  const more = [...container.querySelectorAll("button")].find((b) =>
    b.textContent?.includes("...more"),
  )!;
  await act(async () => more.click());
  const buttons = [...container.querySelectorAll<HTMLElement>("[role=dialog] button")];
  buttons.at(-1)!.focus();

  await act(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", cancelable: true }));
  });

  expect(document.activeElement).toBe(buttons[0]);
});

it("searches the channel from the magnifier", async () => {
  api.GET.mockImplementation(async (path: string, init: { params?: { query?: { q?: string } } }) => {
    if (path === "/api/channels/{username}") return { data: CHANNEL, response: new Response() };
    if (path === "/api/channels/{username}/search") {
      const items = init.params?.query?.q === "rust" ? [card("r", "Rust in 100 Seconds")] : [];
      return { data: { items, next_cursor: null } };
    }
    return { data: { items: [], next_cursor: null } };
  });

  await render();
  await shows("This channel has no videos yet.");
  await act(async () => button("")!.click());
  const input = container.querySelector<HTMLInputElement>("input[type=search]")!;
  await act(async () => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setValue.call(input, "rust");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => input.form!.requestSubmit());
  await shows("Rust in 100 Seconds");

  expect(container.querySelector("[data-testid=where]")?.textContent).toBe(
    "/@ana/search?query=rust",
  );
});

it("says so when a channel search finds nothing", async () => {
  serveLists({});

  await render("/@ana/search?query=haskell");

  await shows('This channel has no videos matching "haskell".');
});
