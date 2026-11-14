// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { WatchPage } from "./WatchPage";

const player = vi.hoisted(() => ({ mounts: 0 }));

vi.mock("../components/VideoPlayer", () => ({
  VideoPlayer: ({ theater, onTheater }: { theater: boolean; onTheater: () => void }) => {
    useEffect(() => {
      player.mounts += 1;
    }, []);
    return (
      <button type="button" data-testid="fake-player" data-theater={theater} onClick={onTheater}>
        player
      </button>
    );
  },
}));
vi.mock("../hooks/useVideo", () => ({
  useVideo: () => ({
    isPending: false,
    isError: false,
    data: {
      id: "v1",
      title: "Sounds Recorded on Mars",
      description: "",
      visibility: "public",
      status: "ready",
      hidden_at: null,
      hidden_reason: null,
      duration_seconds: 21,
      published_at: "2026-01-01T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
      channel: { username: "blue_planet_lab", display_name: "Blue Planet Lab" },
      views_count: 1,
      likes_count: 0,
      dislikes_count: 0,
      comments_count: 0,
      thumbnail_url: null,
      my_reaction: null,
    },
  }),
  statusMessage: () => null,
  VideoNotFound: class extends Error {},
}));
vi.mock("../hooks/usePlaylists", () => ({ usePlaylist: () => ({ data: undefined }) }));
vi.mock("../hooks/useFeed", () => ({ useFeedFirstPage: () => ({ data: [] }) }));
vi.mock("../hooks/useChannel", () => ({ useChannel: () => ({ data: undefined }) }));
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: null, isLoading: false, logout: async () => {} }),
}));
vi.mock("../components/Comments", () => ({ Comments: () => null }));
vi.mock("../components/UpNext", () => ({ UpNext: () => null }));

let container: HTMLDivElement;
let root: Root;

beforeEach(async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  player.mounts = 0;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () =>
    root.render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/watch?v=v1"]}>
          <Routes>
            <Route path="/watch" element={<WatchPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  );
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const fakePlayer = () => container.querySelector<HTMLButtonElement>("[data-testid=fake-player]")!;
const slot = () => container.querySelector("[data-testid=player-slot]")!;

it("switches to theater mode and back without restarting the player", async () => {
  expect(player.mounts).toBe(1);
  expect(slot().className).not.toContain("w-screen");

  await act(async () => fakePlayer().click());
  expect(fakePlayer().dataset.theater).toBe("true");
  expect(slot().className).toContain("w-screen");

  await act(async () => fakePlayer().click());
  expect(fakePlayer().dataset.theater).toBe("false");

  expect(player.mounts).toBe(1);
});

it("remembers theater mode", async () => {
  await act(async () => fakePlayer().click());

  expect(localStorage.getItem("player.theater")).toBe("1");
});
