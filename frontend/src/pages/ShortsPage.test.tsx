// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";

import { ShortsPage } from "./ShortsPage";

const api = vi.hoisted(() => ({ GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn() }));
vi.mock("../api/client", () => ({ api }));
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: null, isLoading: false, logout: async () => {} }),
}));
vi.mock("../components/player/usePlayback", () => ({
  usePlayback: () => ({ failure: null, quality: null }),
  FAILURE_TEXT: {},
}));
vi.mock("../hooks/useViewHeartbeat", () => ({ useViewHeartbeat: () => {} }));
vi.mock("../components/Comments", () => ({ Comments: () => <p>comments here</p> }));

const short = (id: string) => ({
  id,
  title: `Short ${id}`,
  duration_seconds: 15,
  views_count: 10,
  published_at: "2026-01-01T00:00:00Z",
  thumbnail_url: `/thumbs/${id}.jpg`,
  channel: { username: "wild_water", display_name: "Wild Water" },
  is_short: true,
});

const details = (id: string, isShort = true) => ({
  ...short(id),
  description: "",
  visibility: "public",
  status: "ready",
  created_at: "2026-01-01T00:00:00Z",
  likes_count: 1234,
  dislikes_count: 0,
  comments_count: 5,
  my_reaction: null,
  hidden_at: null,
  hidden_reason: null,
  width: isShort ? 1080 : 1920,
  height: isShort ? 1920 : 1080,
  is_short: isShort,
});

const observed: { callback: IntersectionObserverCallback; elements: Element[] }[] = [];

beforeAll(() => {
  class FakeObserver {
    elements: Element[] = [];
    constructor(readonly callback: IntersectionObserverCallback) {
      observed.push(this);
    }
    observe(element: Element) {
      this.elements.push(element);
    }
    disconnect() {}
  }
  vi.stubGlobal("IntersectionObserver", FakeObserver);
  if (!globalThis.CSS?.escape) vi.stubGlobal("CSS", { escape: (value: string) => value });
  Element.prototype.scrollIntoView = vi.fn();
  HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve());
  HTMLMediaElement.prototype.pause = vi.fn();
});

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  observed.length = 0;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  api.GET.mockImplementation(
    async (path: string, init: { params?: { path?: { video_id?: string } } }) => {
      if (path === "/api/videos/shorts") {
        return { data: { items: [short("a"), short("b"), short("c")], next_cursor: null } };
      }
      if (path === "/api/videos/{video_id}") {
        const id = init.params?.path?.video_id ?? "";
        return { data: details(id, id !== "wide"), response: new Response() };
      }
      if (path === "/api/channels/{username}") return { data: undefined, response: new Response() };
      return { data: undefined };
    },
  );
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

function Where() {
  const { pathname, search } = useLocation();
  return <output data-testid="where">{pathname + search}</output>;
}

async function render(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () =>
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/shorts" element={<ShortsPage />} />
            <Route path="/shorts/:id" element={<ShortsPage />} />
            <Route path="/watch" element={<p>watch page</p>} />
            <Route path="/login" element={<p>login page</p>} />
          </Routes>
          <Where />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  );
}

const where = () => container.querySelector("[data-testid=where]")?.textContent;
async function settle(check: () => void) {
  await vi.waitFor(async () => {
    await act(async () => {});
    check();
  });
}

it("opens the newest Short at /shorts", async () => {
  await render("/shorts");

  await settle(() => expect(where()).toBe("/shorts/a"));
});

it("plays only the Short on screen, with its actions", async () => {
  await render("/shorts/b");
  await settle(() => expect(container.querySelectorAll("video")).toHaveLength(1));

  const sections = [...container.querySelectorAll("section[data-short]")];
  expect(sections.map((s) => s.getAttribute("data-short"))).toEqual(["a", "b", "c"]);
  expect(sections[1]!.querySelector("video")).not.toBeNull();
  await settle(() => expect(container.textContent).toContain("1.2K"));
  expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
});

it("moves to whichever Short scrolls into view", async () => {
  await render("/shorts/a");
  await settle(() => expect(observed.at(-1)?.elements.length).toBe(3));
  const observer = observed.at(-1)!;
  const target = observer.elements.find((e) => e.getAttribute("data-short") === "c")!;

  await act(async () =>
    observer.callback(
      [{ isIntersecting: true, target } as unknown as IntersectionObserverEntry],
      {} as IntersectionObserver,
    ),
  );

  expect(container.querySelector("section[data-short=c] video")).not.toBeNull();
  expect(container.querySelector("section[data-short=a] video")).toBeNull();
  expect(window.location.pathname).toBe("/shorts/c");
});

it("sends a regular video to the watch page", async () => {
  await render("/shorts/wide");

  await settle(() => expect(where()).toBe("/watch?v=wide"));
});

it("asks a signed-out viewer to sign in before liking", async () => {
  await render("/shorts/a");
  const like = await vi.waitFor(() => {
    const button = container.querySelector<HTMLButtonElement>("button[aria-label=Like]");
    expect(button).not.toBeNull();
    return button!;
  });

  await act(async () => like.click());

  expect(where()).toBe(`/login?next=${encodeURIComponent("/shorts/a")}`);
});

it("opens the comments beside the Short", async () => {
  await render("/shorts/a");
  const comments = await vi.waitFor(() => {
    const button = container.querySelector<HTMLButtonElement>("button[aria-label=Comments]");
    expect(button).not.toBeNull();
    return button!;
  });

  await act(async () => comments.click());

  expect(container.textContent).toContain("comments here");
});

it("remembers muting across Shorts", async () => {
  await render("/shorts/a");
  const mute = await vi.waitFor(() => {
    const button = container.querySelector<HTMLButtonElement>("button[aria-label='Mute (m)']");
    expect(button).not.toBeNull();
    return button!;
  });

  await act(async () => mute.click());

  expect(localStorage.getItem("shorts.muted")).toBe("1");
  expect(container.querySelector("video")!.muted).toBe(true);
});

it("goes to the next Short with the arrow key", async () => {
  await render("/shorts/a");
  await settle(() => expect(container.querySelectorAll("section[data-short]")).toHaveLength(3));
  vi.mocked(Element.prototype.scrollIntoView).mockClear();

  await act(async () => {
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
  });

  const scrolled = vi.mocked(Element.prototype.scrollIntoView).mock.contexts[0] as Element;
  expect(scrolled.getAttribute("data-short")).toBe("b");
});
