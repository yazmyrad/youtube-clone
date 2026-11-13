import { describe, expect, it, vi } from "vitest";

import { createApi } from "../api/client";
import { changeItems, moved, playlistKey } from "./usePlaylists";

function client(status = 200, body: unknown = { id: "p1", items: [] }) {
  const requests: Request[] = [];
  const fetchFn = vi.fn(async (request: Request) => {
    requests.push(request.clone());
    return Response.json(body, { status });
  });
  return { api: createApi("http://test", fetchFn), requests };
}

describe("moved", () => {
  it("swaps with the neighbour above or below", () => {
    expect(moved(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
    expect(moved(["a", "b", "c"], 1, 1)).toEqual(["a", "c", "b"]);
  });

  it("leaves the ends alone", () => {
    expect(moved(["a", "b"], 0, -1)).toEqual(["a", "b"]);
    expect(moved(["a", "b"], 1, 1)).toEqual(["a", "b"]);
  });
});

describe("changeItems", () => {
  it("removes with a DELETE", async () => {
    const { api, requests } = client();

    await changeItems(api, "p1", { kind: "remove", videoId: "v1" });

    expect(requests[0]?.method).toBe("DELETE");
    expect(new URL(requests[0]?.url ?? "").pathname).toBe("/api/playlists/p1/items/v1");
  });

  it("reorders with a PUT of the whole order", async () => {
    const { api, requests } = client();

    await changeItems(api, "p1", { kind: "order", videoIds: ["b", "a"] });

    expect(requests[0]?.method).toBe("PUT");
    expect(new URL(requests[0]?.url ?? "").pathname).toBe("/api/playlists/p1/items/order");
    await expect(requests[0]?.json()).resolves.toEqual({ video_ids: ["b", "a"] });
  });

  it("reports the server's reason", async () => {
    const { api } = client(409, { detail: "The playlist has changed. Reload it and try again" });

    await expect(changeItems(api, "p1", { kind: "order", videoIds: [] })).rejects.toThrow(
      "The playlist has changed",
    );
  });
});

it("keys a playlist by account", () => {
  expect(playlistKey("p1", "ana")).not.toEqual(playlistKey("p1", null));
});
