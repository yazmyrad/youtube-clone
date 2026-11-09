import { describe, expect, it, vi } from "vitest";

import { createApi } from "../api/client";
import { cleanComment, fetchComments, postComment } from "./useComments";

function client(status: number, body: unknown) {
  const requests: Request[] = [];
  const fetchFn = vi.fn(async (request: Request) => {
    requests.push(request.clone());
    return Response.json(body, { status });
  });
  return { api: createApi("http://test", fetchFn), requests };
}

describe("cleanComment", () => {
  it("trims what it sends", () => {
    expect(cleanComment("  nice video \n")).toBe("nice video");
  });

  it("refuses an empty comment", () => {
    expect(cleanComment("  \n\t ")).toBeNull();
  });
});

describe("fetchComments", () => {
  const PAGE = { items: [], next_cursor: null };

  it("asks for the first page without a cursor", async () => {
    const { api, requests } = client(200, PAGE);

    await expect(fetchComments(api, "v1", undefined)).resolves.toEqual(PAGE);

    const url = new URL(requests[0]?.url ?? "");
    expect(url.pathname).toBe("/api/videos/v1/comments");
    expect(url.searchParams.has("cursor")).toBe(false);
  });

  it("passes the cursor for later pages", async () => {
    const { api, requests } = client(200, PAGE);

    await fetchComments(api, "v1", "abc");

    expect(new URL(requests[0]?.url ?? "").searchParams.get("cursor")).toBe("abc");
  });

  it("reports the server's reason", async () => {
    const { api } = client(404, { detail: "Video not found" });

    await expect(fetchComments(api, "v1", undefined)).rejects.toThrow("Video not found");
  });
});

describe("postComment", () => {
  it("posts the body", async () => {
    const created = { id: "c1", body: "hi" };
    const { api, requests } = client(201, created);

    await expect(postComment(api, "v1", "hi")).resolves.toEqual(created);

    expect(requests[0]?.method).toBe("POST");
    await expect(requests[0]?.json()).resolves.toEqual({ body: "hi" });
  });

  it("reports a refused comment", async () => {
    const { api } = client(409, { detail: "The video isn't ready yet" });

    await expect(postComment(api, "v1", "hi")).rejects.toThrow("The video isn't ready yet");
  });
});
