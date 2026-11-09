import { describe, expect, it, vi } from "vitest";

import { authMiddleware, createApi, requestRefresh } from "./client";
import { createSession, type SessionDeps } from "./session";

const yieldToOthers = () => new Promise<void>((done) => setTimeout(done, 0));

function memoryStorage() {
  const items = new Map<string, string>();
  return {
    items,
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
    removeItem: (key: string) => void items.delete(key),
  };
}

/** A shared clock and storage: every session made from one World is a tab of one browser. */
function world() {
  const storage = memoryStorage();
  let time = 1_000_000;
  const sleep = async (ms: number) => {
    time += ms;
    await yieldToOthers();
  };
  let issued = 0;
  let active = 0;
  const stats = { calls: 0, maxActive: 0 };
  const okRefresh: SessionDeps["refreshRequest"] = async () => {
    stats.calls += 1;
    active += 1;
    stats.maxActive = Math.max(stats.maxActive, active);
    await sleep(20);
    active -= 1;
    issued += 1;
    return `token-${issued}`;
  };
  const tab = (refreshRequest = okRefresh) =>
    createSession({ refreshRequest, storage: () => storage, now: () => time, sleep });
  return { storage, tab, stats, advance: (ms: number) => (time += ms), now: () => time };
}

describe("session refresh", () => {
  it("shares one request between concurrent calls in a tab", async () => {
    const { tab, stats } = world();
    const session = tab();

    const results = await Promise.all([session.refresh(), session.refresh(), session.refresh()]);

    expect(stats.calls).toBe(1);
    expect(results).toEqual(["token-1", "token-1", "token-1"]);
    expect(session.getToken()).toBe("token-1");
  });

  it("makes a second tab wait for the first, so a token is never used twice", async () => {
    const { tab, stats } = world();
    const [first, second] = [tab(), tab()];

    const results = await Promise.all([first.refresh(), second.refresh()]);

    expect(stats.calls).toBe(2);
    expect(stats.maxActive).toBe(1);
    expect(results).toEqual(["token-1", "token-2"]);
  });

  it("takes over a lease left behind by a closed tab", async () => {
    const { storage, tab, stats, now } = world();
    storage.setItem("auth.refresh.lease", JSON.stringify({ id: "dead", expires: now() - 1 }));

    await tab().refresh();

    expect(stats.calls).toBe(1);
  });

  it("releases the lease afterwards", async () => {
    const { storage, tab } = world();

    await tab().refresh();

    expect(storage.items.size).toBe(0);
  });

  it("gives up rather than refresh while another tab holds the lease", async () => {
    const { storage, tab, stats, now } = world();
    const lease = { id: "other", expires: now() + 10 ** 9 };
    storage.setItem("auth.refresh.lease", JSON.stringify(lease));

    const session = tab();
    const lost = vi.fn();
    session.onLost(lost);
    session.setToken("still-good");

    await expect(session.refresh()).resolves.toBeNull();

    expect(stats.calls).toBe(0);
    expect(session.getToken()).toBe("still-good");
    expect(lost).not.toHaveBeenCalled();
  });

  it("still refreshes when storage is unavailable", async () => {
    const refreshRequest = vi.fn(async () => "token");
    const session = createSession({
      refreshRequest,
      storage: () => {
        throw new Error("denied");
      },
    });

    await expect(session.refresh()).resolves.toBe("token");
  });

  it("clears the session and reports it when the refresh is refused", async () => {
    const { tab } = world();
    const session = tab(async () => null);
    const lost = vi.fn();
    session.onLost(lost);
    session.setToken("old");

    await expect(session.refresh()).resolves.toBeNull();

    expect(session.getToken()).toBeNull();
    expect(lost).toHaveBeenCalledOnce();
  });

  it("keeps the session when the server can't answer", async () => {
    const { tab } = world();
    const session = tab(() => Promise.reject(new Error("offline")));
    const lost = vi.fn();
    session.onLost(lost);
    session.setToken("still-good");

    await expect(session.refresh()).resolves.toBeNull();

    expect(session.getToken()).toBe("still-good");
    expect(lost).not.toHaveBeenCalled();
  });

  it("doesn't report a lost session for a visitor who never had one", async () => {
    const { tab } = world();
    const session = tab(async () => null);
    const lost = vi.fn();
    session.onLost(lost);

    await session.refresh();

    expect(lost).not.toHaveBeenCalled();
  });

  it("doesn't let a refresh already under way undo a logout", async () => {
    const { tab } = world();
    const session = tab();
    session.setToken("old");

    const refreshing = session.refresh();
    session.clear();
    await refreshing;

    expect(session.getToken()).toBeNull();
  });
});

describe("requestRefresh", () => {
  const respondWith = (status: number, body = "{}") =>
    createApi(
      "http://test",
      async () => new Response(body, { status, headers: { "Content-Type": "application/json" } }),
    );
  const signal = new AbortController().signal;

  it("returns the new token", async () => {
    const client = respondWith(200, '{"access_token":"new","expires_in":900}');

    await expect(requestRefresh(client, signal)).resolves.toBe("new");
  });

  it("reports a refused cookie as null", async () => {
    await expect(requestRefresh(respondWith(401), signal)).resolves.toBeNull();
  });

  it.each([403, 500, 502, 503])("throws on %i, which doesn't end the session", async (status) => {
    await expect(requestRefresh(respondWith(status), signal)).rejects.toThrow();
  });
});

describe("authMiddleware", () => {
  function setup(respond: (request: Request) => Response) {
    const { tab, stats } = world();
    const session = tab();
    const seen: { url: string; authorization: string | null }[] = [];
    const fetchFn = vi.fn(async (request: Request) => {
      seen.push({
        url: new URL(request.url).pathname,
        authorization: request.headers.get("Authorization"),
      });
      return respond(request);
    });
    const api = createApi("http://test", fetchFn);
    api.use(authMiddleware(session, fetchFn));
    return { api, session, stats, seen };
  }

  const json = (status: number) =>
    new Response("{}", { status, headers: { "Content-Type": "application/json" } });
  const acceptOnlyFreshTokens = (request: Request) =>
    json(request.headers.get("Authorization")?.startsWith("Bearer token-") ? 200 : 401);

  it("refreshes once for concurrent 401s and retries each request", async () => {
    const { api, session, stats } = setup(acceptOnlyFreshTokens);
    session.setToken("expired");

    const responses = await Promise.all([api.GET("/api/users/me"), api.GET("/api/users/me")]);

    expect(stats.calls).toBe(1);
    expect(responses.map((result) => result.response.status)).toEqual([200, 200]);
  });

  it("uses the token that replaced it for a 401 that arrives late", async () => {
    // The token changes while the first request is on the wire.
    const { api, session, stats, seen } = setup((request) => {
      if (request.headers.get("Authorization") === "Bearer expired") {
        session.setToken("token-from-login");
        return json(401);
      }
      return json(200);
    });
    session.setToken("expired");

    const { response } = await api.GET("/api/users/me");

    expect(response.status).toBe(200);
    expect(stats.calls).toBe(0);
    expect(seen.map((request) => request.authorization)).toEqual([
      "Bearer expired",
      "Bearer token-from-login",
    ]);
  });

  it("resends the request body on the retry", async () => {
    const bodies: string[] = [];
    const { tab } = world();
    const session = tab();
    const fetchFn = async (request: Request) => {
      bodies.push(await request.text());
      return acceptOnlyFreshTokens(request);
    };
    const api = createApi("http://test", fetchFn);
    api.use(authMiddleware(session, fetchFn));
    session.setToken("expired");

    await api.PATCH("/api/users/me", { body: { display_name: "Ana" } });

    expect(bodies).toEqual(['{"display_name":"Ana"}', '{"display_name":"Ana"}']);
  });

  it("returns the 401 when the refresh fails", async () => {
    const { tab } = world();
    const session = tab(async () => null);
    const fetchFn = vi.fn(async () => json(401));
    const api = createApi("http://test", fetchFn);
    api.use(authMiddleware(session, fetchFn));
    session.setToken("expired");

    const { response } = await api.GET("/api/users/me");

    expect(response.status).toBe(401);
    expect(fetchFn).toHaveBeenCalledOnce();
  });

  it("neither sends the token to nor retries auth routes", async () => {
    const { api, session, stats, seen } = setup(() => json(401));
    session.setToken("token");

    await api.POST("/api/auth/login", { body: { email: "a@b.co", password: "wrong-pass" } });

    expect(stats.calls).toBe(0);
    expect(seen).toEqual([{ url: "/api/auth/login", authorization: null }]);
  });

  it("tries one restore for a visitor with no session, and doesn't retry their 401s", async () => {
    const refreshRequest = vi.fn(async () => null);
    const session = world().tab(refreshRequest);
    const fetchFn = vi.fn(async () => json(401));
    const api = createApi("http://test", fetchFn);
    api.use(authMiddleware(session, fetchFn));

    await Promise.all([api.GET("/api/users/me"), api.GET("/api/users/me")]);
    await api.GET("/api/users/me");

    expect(refreshRequest).toHaveBeenCalledOnce();
    expect(fetchFn).toHaveBeenCalledTimes(3);
  });

  it("holds a page's first request until the session is restored", async () => {
    let finishRestore: (token: string) => void = () => {};
    const refreshRequest = vi.fn(
      () => new Promise<string>((resolve) => (finishRestore = resolve)),
    );
    const session = world().tab(refreshRequest);
    const authorizations: (string | null)[] = [];
    const fetchFn = async (request: Request) => {
      authorizations.push(request.headers.get("Authorization"));
      return json(200);
    };
    const api = createApi("http://test", fetchFn);
    api.use(authMiddleware(session, fetchFn));

    const fetching = api.GET("/api/users/me");
    await vi.waitFor(() => expect(refreshRequest).toHaveBeenCalled());
    expect(authorizations).toEqual([]);

    finishRestore("restored");
    await fetching;

    expect(authorizations).toEqual(["Bearer restored"]);
  });

  it("doesn't wait for a restore on auth routes", async () => {
    const refreshRequest = vi.fn(() => new Promise<string>(() => {}));
    const session = world().tab(refreshRequest);
    const fetchFn = vi.fn(async () => json(401));
    const api = createApi("http://test", fetchFn);
    api.use(authMiddleware(session, fetchFn));

    await api.POST("/api/auth/login", { body: { email: "a@b.co", password: "wrong-pass" } });

    expect(refreshRequest).not.toHaveBeenCalled();
    expect(fetchFn).toHaveBeenCalledOnce();
  });
});
