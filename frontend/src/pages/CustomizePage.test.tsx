// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { CustomizePage } from "./CustomizePage";

const api = vi.hoisted(() => ({ PUT: vi.fn(), DELETE: vi.fn(), PATCH: vi.fn() }));
vi.mock("../api/client", () => ({ api }));

const ME = {
  id: "u1",
  username: "ana",
  email: "ana@example.com",
  display_name: "Ana Codes",
  description: "Code",
  role: "user",
  subscribers_count: 0,
  avatar_url: null as string | null,
  banner_url: null as string | null,
  created_at: "2026-01-01T00:00:00Z",
};
const auth = vi.hoisted(() => ({ user: null as object | null }));
vi.mock("../hooks/useAuth", () => ({
  ME_KEY: ["me"],
  useAuth: () => ({ user: auth.user, isLoading: false }),
}));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  auth.user = ME;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
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

async function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () =>
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/customize"]}>
          <Routes>
            <Route path="/customize" element={<CustomizePage />} />
            <Route path="/login" element={<p>login page</p>} />
          </Routes>
          <Where />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  );
}

async function choose(label: string, file: File) {
  const input = container.querySelector<HTMLInputElement>(`input[aria-label='${label}']`)!;
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
}

function button(name: string) {
  return [...container.querySelectorAll("button")].find((b) => b.textContent === name);
}

it("sends a signed-out visitor to log in", async () => {
  auth.user = null;

  await render();

  expect(container.querySelector("[data-testid=where]")?.textContent).toBe(
    "/login?next=/customize",
  );
});

it("uploads the picture as the request body, with its type", async () => {
  api.PUT.mockResolvedValue({ data: { ...ME, avatar_url: "/channel-images/a.webp" } });
  const file = new File(["jpeg bytes"], "me.jpg", { type: "image/jpeg" });

  await render();
  await choose("Choose a picture", file);

  await vi.waitFor(() => expect(api.PUT).toHaveBeenCalled());
  const [path, init] = api.PUT.mock.calls[0]!;
  expect(path).toBe("/api/users/me/images/{kind}");
  expect(init.params).toEqual({ path: { kind: "avatar" } });
  expect(init.headers).toEqual({ "Content-Type": "image/jpeg" });
  expect(init.bodySerializer(init.body)).toBe(file);
});

it.each([
  [new File(["gif"], "a.gif", { type: "image/gif" }), "Choose a JPEG, PNG or WebP image."],
  [
    new File([new Uint8Array(6 * 1024 * 1024 + 1)], "big.png", { type: "image/png" }),
    "Choose an image of at most 6 MB.",
  ],
])("refuses %s before sending it", async (file, message) => {
  await render();
  await choose("Choose a banner", file);

  expect(api.PUT).not.toHaveBeenCalled();
  expect(container.querySelector("[role=alert]")?.textContent).toBe(message);
});

it("shows the server's reason when an upload is refused", async () => {
  api.PUT.mockResolvedValue({ error: { detail: "The image is too small" } });

  await render();
  await choose("Choose a banner", new File(["png"], "b.png", { type: "image/png" }));

  await vi.waitFor(() =>
    expect(container.querySelector("[role=alert]")?.textContent).toContain("too small"),
  );
});

it("removes the banner", async () => {
  auth.user = { ...ME, banner_url: "/channel-images/b.webp" };
  api.DELETE.mockResolvedValue({ data: ME });

  await render();
  await act(async () => button("Remove")!.click());

  expect(api.DELETE).toHaveBeenCalledWith("/api/users/me/images/{kind}", {
    params: { path: { kind: "banner" } },
  });
});

it("publishes a new name and description", async () => {
  api.PATCH.mockResolvedValue({ data: { ...ME, display_name: "Ana" } });

  await render();
  expect(button("Publish")?.disabled).toBe(true);
  const name = container.querySelector<HTMLInputElement>("input:not([type=file])")!;
  await act(async () => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setValue.call(name, "  Ana  ");
    name.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => button("Publish")!.click());

  expect(api.PATCH).toHaveBeenCalledWith("/api/users/me", {
    body: { display_name: "Ana", description: "Code" },
  });
});
