// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { VideoDetails } from "../hooks/useVideo";
import { HiddenNotice } from "./HiddenNotice";
import { HideButton } from "./HideButton";
import { ReportButton } from "./ReportButton";

const api = vi.hoisted(() => ({ POST: vi.fn() }));
vi.mock("../api/client", () => ({ api }));

const auth = vi.hoisted(() => ({ user: null as { username: string; role: string } | null }));
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: auth.user, isLoading: false, logout: async () => {} }),
}));

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
  api.POST.mockReset();
  auth.user = null;
});

function Where() {
  const { pathname, search } = useLocation();
  return <output data-testid="where">{pathname + search}</output>;
}

async function render(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/watch?v=v1"]}>
          <Routes>
            <Route path="*" element={element} />
          </Routes>
          <Where />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
}

const buttonNamed = (text: string) =>
  [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === text);

async function settle(check: () => void) {
  await vi.waitFor(async () => {
    await act(async () => {});
    check();
  });
}

function type(element: HTMLTextAreaElement, value: string) {
  const setValue = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  setValue.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
}

it("sends a signed-out visitor to log in before reporting", async () => {
  await render(<ReportButton videoId="v1" owner="ana" />);

  await act(async () => buttonNamed("Report")!.click());

  expect(container.querySelector("[data-testid=where]")?.textContent).toBe(
    `/login?next=${encodeURIComponent("/watch?v=v1")}`,
  );
});

it("isn't offered on your own video", async () => {
  auth.user = { username: "ana", role: "user" };
  await render(<ReportButton videoId="v1" owner="ana" />);

  expect(buttonNamed("Report")).toBeUndefined();
});

it("reports with a reason and details, then thanks", async () => {
  auth.user = { username: "bob", role: "user" };
  api.POST.mockResolvedValue({ data: { id: "r1" }, response: new Response() });
  await render(<ReportButton videoId="v1" owner="ana" />);

  await act(async () => buttonNamed("Report")!.click());
  const submit = () =>
    [...container.querySelectorAll<HTMLButtonElement>("button[type=submit]")][0]!;
  expect(submit().disabled).toBe(true);
  await act(async () =>
    container.querySelector<HTMLInputElement>("input[value=copyright]")!.click(),
  );
  await act(async () => type(container.querySelector("textarea")!, "  My song  "));
  await act(async () => submit().click());

  await settle(() => expect(container.textContent).toContain("Thanks for reporting"));
  expect(api.POST).toHaveBeenCalledWith("/api/videos/{video_id}/reports", {
    params: { path: { video_id: "v1" } },
    body: { reason: "copyright", details: "My song" },
  });
});

it("says so when already reported", async () => {
  auth.user = { username: "bob", role: "user" };
  api.POST.mockResolvedValue({
    error: { detail: "You've already reported this video" },
    response: new Response(null, { status: 409 }),
  });
  await render(<ReportButton videoId="v1" owner="ana" />);

  await act(async () => buttonNamed("Report")!.click());
  await act(async () => container.querySelector<HTMLInputElement>("input[value=spam]")!.click());
  await act(async () => container.querySelector<HTMLButtonElement>("button[type=submit]")!.click());

  await settle(() =>
    expect(container.querySelector("[role=alert]")?.textContent).toBe(
      "You've already reported this video",
    ),
  );
});

it("offers Hide to moderators only, and hides with a reason", async () => {
  auth.user = { username: "bob", role: "user" };
  await render(<HideButton videoId="v1" />);
  expect(buttonNamed("Hide")).toBeUndefined();

  auth.user = { username: "mod", role: "moderator" };
  api.POST.mockResolvedValue({ data: { reports_closed: 1 }, response: new Response() });
  await render(<HideButton videoId="v1" />);
  await act(async () => buttonNamed("Hide")!.click());
  await act(async () => type(container.querySelector("textarea")!, " Spam links "));
  await act(async () => container.querySelector<HTMLButtonElement>("button[type=submit]")!.click());

  await settle(() => expect(container.querySelector("[role=dialog]")).toBeNull());
  expect(api.POST).toHaveBeenCalledWith("/api/moderation/videos/{video_id}/hide", {
    params: { path: { video_id: "v1" } },
    body: { reason: "Spam links" },
  });
});

const hiddenVideo = {
  id: "v1",
  hidden_at: "2026-01-01T00:00:00Z",
  hidden_reason: "Spam links",
} as VideoDetails;

it("tells the owner why their video was hidden, without Restore", async () => {
  auth.user = { username: "ana", role: "user" };
  await render(<HiddenNotice video={hiddenVideo} />);

  expect(container.textContent).toContain("This video was hidden by a moderator.");
  expect(container.textContent).toContain("Reason: Spam links");
  expect(buttonNamed("Restore video")).toBeUndefined();
});

it("lets a moderator restore a hidden video", async () => {
  auth.user = { username: "mod", role: "admin" };
  api.POST.mockResolvedValue({ response: new Response(null, { status: 204 }) });
  await render(<HiddenNotice video={hiddenVideo} />);

  await act(async () => buttonNamed("Restore video")!.click());

  await settle(() =>
    expect(api.POST).toHaveBeenCalledWith("/api/moderation/videos/{video_id}/restore", {
      params: { path: { video_id: "v1" } },
      body: { reason: "" },
    }),
  );
});
