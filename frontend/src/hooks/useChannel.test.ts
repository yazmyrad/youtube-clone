import { describe, expect, it, vi } from "vitest";

import { createApi } from "../api/client";
import { channelKey, sendSubscription } from "./useChannel";

const STATE = { is_subscribed: true, subscribers_count: 4 };

function client(status = 200, body: unknown = STATE) {
  const requests: Request[] = [];
  const fetchFn = vi.fn(async (request: Request) => {
    requests.push(request.clone());
    return Response.json(body, { status });
  });
  return { api: createApi("http://test", fetchFn), requests };
}

describe("sendSubscription", () => {
  it("subscribes with a PUT", async () => {
    const { api, requests } = client();

    await expect(sendSubscription(api, "ana", true)).resolves.toEqual(STATE);

    expect(requests[0]?.method).toBe("PUT");
    expect(new URL(requests[0]?.url ?? "").pathname).toBe("/api/channels/ana/subscription");
  });

  it("unsubscribes with a DELETE", async () => {
    const { api, requests } = client();

    await sendSubscription(api, "ana", false);

    expect(requests[0]?.method).toBe("DELETE");
  });

  it("reports the server's reason", async () => {
    const { api } = client(403, { detail: "You can't subscribe to your own channel" });

    await expect(sendSubscription(api, "ana", true)).rejects.toThrow(
      "You can't subscribe to your own channel",
    );
  });
});

describe("channelKey", () => {
  it("ignores the case of the username, as the server does", () => {
    expect(channelKey("Ana", null)).toEqual(channelKey("ana", null));
  });

  it("differs per account", () => {
    expect(channelKey("ana", "bob")).not.toEqual(channelKey("ana", null));
  });
});
