import { describe, expect, it, vi } from "vitest";

import { createApi } from "../api/client";
import { nextReaction, sendReaction, withReactionState } from "./useReaction";
import type { VideoDetails } from "./useVideo";

const STATE = { my_reaction: "like", likes_count: 3, dislikes_count: 1 } as const;

function client(status = 200, body: unknown = STATE) {
  const requests: Request[] = [];
  const fetchFn = vi.fn(async (request: Request) => {
    requests.push(request.clone());
    return Response.json(body, { status });
  });
  return { api: createApi("http://test", fetchFn), requests };
}

describe("nextReaction", () => {
  it("sets a reaction when there is none", () => {
    expect(nextReaction(null, "like")).toBe("like");
  });

  it("takes back the active one", () => {
    expect(nextReaction("like", "like")).toBeNull();
  });

  it("switches to the other one", () => {
    expect(nextReaction("like", "dislike")).toBe("dislike");
  });
});

describe("sendReaction", () => {
  it("sends a PUT with the reaction", async () => {
    const { api, requests } = client();

    await expect(sendReaction(api, "v1", "like")).resolves.toEqual(STATE);

    expect(requests[0]?.method).toBe("PUT");
    expect(new URL(requests[0]?.url ?? "").pathname).toBe("/api/videos/v1/reaction");
    await expect(requests[0]?.json()).resolves.toEqual({ reaction: "like" });
  });

  it("sends a DELETE to take it back", async () => {
    const { api, requests } = client();

    await sendReaction(api, "v1", null);

    expect(requests[0]?.method).toBe("DELETE");
  });

  it("reports the server's reason", async () => {
    const { api } = client(409, { detail: "The video isn't ready yet" });

    await expect(sendReaction(api, "v1", "like")).rejects.toThrow("The video isn't ready yet");
  });
});

describe("withReactionState", () => {
  it("updates the counters and keeps the rest of the video", () => {
    const video = {
      title: "Clip",
      my_reaction: null,
      likes_count: 2,
      dislikes_count: 1,
    } as VideoDetails;

    expect(withReactionState(video, STATE)).toEqual({ title: "Clip", ...STATE });
  });
});
