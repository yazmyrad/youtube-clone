import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToString } from "react-dom/server";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { expect, it, vi } from "vitest";

import { appRoutes } from "./router";

vi.mock("./hooks/useAuth", () => ({
  useAuth: () => ({
    user: { username: "ana", display_name: "Ana" },
    isLoading: false,
    logout: async () => {},
  }),
}));

function render(path: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  return renderToString(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

it("renders the upload form, whose leave guard needs a data router", () => {
  const html = render("/upload");

  expect(html).toContain("Upload video");
  expect(html).toContain("Drag and drop a video");
});

it("opens the watch page for a video id", () => {
  const html = render("/watch?v=a7f3");

  expect(html).toContain("aspect-video");
  expect(html).not.toContain("The link may be broken");
});

it("has nothing to show on the watch page without a video id", () => {
  expect(render("/watch")).toContain("The link may be broken");
});

it("opens a channel page at /@username", () => {
  const html = render("/@ana");

  expect(html).not.toContain("The link may be broken");
});

it("has no channel page without the @", () => {
  expect(render("/ana")).toContain("The link may be broken");
});

it("opens a channel's tabs, and nothing else under it", () => {
  expect(render("/@ana/playlists")).not.toContain("The link may be broken");
  expect(render("/@ana/videos")).not.toContain("The link may be broken");
  expect(render("/@ana/about-us")).toContain("The link may be broken");
});

it("opens a playlist by its list parameter", () => {
  expect(render("/playlist?list=p1")).not.toContain("The link may be broken");
  expect(render("/playlist")).toContain("The link may be broken");
});

it("opens the watch page inside a playlist", () => {
  expect(render("/watch?v=a7f3&list=p1")).toContain("aspect-video");
});
