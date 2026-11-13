// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ModerationPage } from "./ModerationPage";

const api = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }));
vi.mock("../api/client", () => ({ api }));

const auth = vi.hoisted(() => ({ user: null as { username: string; role: string } | null }));
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: auth.user, isLoading: false, logout: async () => {} }),
}));

const ENTRY = {
  video: {
    id: "v1",
    title: "Free crypto",
    visibility: "public",
    status: "ready",
    hidden_at: null,
    channel: { username: "spammer", display_name: "Spammer" },
  },
  thumbnail_url: "/thumbs/v1.jpg",
  open_reports: 2,
  reasons: { spam: 2 },
  first_reported_at: "2026-01-01T00:00:00Z",
  reports: [
    {
      id: "r2",
      reason: "spam",
      details: "Scam link",
      reporter: { username: "bob" },
      created_at: "2026-01-02T00:00:00Z",
    },
    {
      id: "r1",
      reason: "spam",
      details: "",
      reporter: { username: "carol" },
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
};

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
  auth.user = null;
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
        <MemoryRouter initialEntries={["/moderation"]}>
          <ModerationPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

const buttonNamed = (text: string) =>
  [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === text);

it.each([null, "user"])("is not found for %s", async (role) => {
  auth.user = role ? { username: "bob", role } : null;

  await render();

  await shows("This page isn't available");
  expect(api.GET).not.toHaveBeenCalled();
});

it("shows each reported video with its reports", async () => {
  auth.user = { username: "mod", role: "moderator" };
  api.GET.mockResolvedValue({ data: { items: [ENTRY], next_cursor: null } });

  await render();
  await shows("Free crypto");

  expect(container.textContent).toContain("2 open reports");
  expect(container.textContent).toContain("Spam or misleading × 2");
  expect(container.textContent).toContain("@bob");
  expect(container.textContent).toContain("Scam link");
  expect(buttonNamed("Hide")).toBeDefined();
});

it.each([
  ["Mark resolved", "/api/moderation/reports/{report_id}/resolve"],
  ["Dismiss", "/api/moderation/reports/{report_id}/dismiss"],
])("%s closes the video's reports", async (label, path) => {
  auth.user = { username: "mod", role: "admin" };
  api.GET.mockResolvedValue({ data: { items: [ENTRY], next_cursor: null } });
  api.POST.mockResolvedValue({ data: { reports_closed: 2 }, response: new Response() });

  await render();
  await shows("Free crypto");
  await act(async () => buttonNamed(label)!.click());

  await vi.waitFor(() =>
    expect(api.POST).toHaveBeenCalledWith(path, {
      params: { path: { report_id: "r2" } },
      body: { reason: "" },
    }),
  );
});

it("says when there's nothing to do", async () => {
  auth.user = { username: "mod", role: "moderator" };
  api.GET.mockResolvedValue({ data: { items: [], next_cursor: null } });

  await render();

  await shows("No open reports. All caught up.");
});
