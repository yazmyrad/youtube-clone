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

it("renders the upload form, whose leave guard needs a data router", () => {
  const router = createMemoryRouter(appRoutes, { initialEntries: ["/upload"] });

  const html = renderToString(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );

  expect(html).toContain("Upload video");
  expect(html).toContain("Drag and drop a video");
});
