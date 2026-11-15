import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

describe("a slow refresh", () => {
  beforeEach(() => void vi.useFakeTimers());
  afterEach(() => void vi.useRealTimers());

  function slowTab(storage: ReturnType<typeof memoryStorage>) {
    const signals: AbortSignal[] = [];
    let finish: (token: string) => void = () => {};
    const session = createSession({
      storage: () => storage,
      refreshRequest: (signal) => {
        signals.push(signal);
        return new Promise<string>((resolve) => (finish = resolve));
      },
    });
    return { session, signals, finish: (token: string) => finish(token) };
  }

  it("isn't abandoned before nginx answers, and keeps other tabs waiting", async () => {
    const storage = memoryStorage();
    const first = slowTab(storage);
    const secondRequest = vi.fn(async () => "second");
    const second = createSession({ storage: () => storage, refreshRequest: secondRequest });

    const firstResult = first.session.refresh();
    await vi.advanceTimersByTimeAsync(100);
    const secondResult = second.refresh();
    await vi.advanceTimersByTimeAsync(59_000);

    expect(first.signals[0]?.aborted).toBe(false);
    expect(secondRequest).not.toHaveBeenCalled();

    first.finish("first");
    await vi.advanceTimersByTimeAsync(1_000);

    await expect(firstResult).resolves.toBe("first");
    await expect(secondResult).resolves.toBe("second");
  });

  it("gives up after the timeout and keeps the session", async () => {
    const storage = memoryStorage();
    const session = createSession({
      storage: () => storage,
      refreshRequest: (signal) =>
        new Promise<string>((_resolve, reject) => {
          signal.addEventListener("abort", () => reject(new Error("aborted")));
        }),
    });
    session.setToken("still-good");

    const result = session.refresh();
    await vi.advanceTimersByTimeAsync(66_000);

    await expect(result).resolves.toBeNull();
    expect(session.getToken()).toBe("still-good");
    expect(storage.items.size).toBe(0);
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

  const jwt = (sub: string, serial: number) =>
    `header.${btoa(JSON.stringify({ sub, serial })).replace(/=+$/, "")}.signature`;

  function accountSetup(refreshed: string) {
    const session = world().tab(async () => refreshed);
    const old = jwt("user-x", 1);
    const fetchFn = vi.fn(async (request: Request) =>
      json(request.headers.get("Authorization") === `Bearer ${old}` ? 401 : 200),
    );
    const api = createApi("http://test", fetchFn);
    api.use(authMiddleware(session, fetchFn));
    const changed = vi.fn();
    session.onAccountChanged(changed);
    session.setToken(old);
    return { api, session, fetchFn, changed };
  }

  it("never replays a request as the user another tab logged in", async () => {
    const other = jwt("user-y", 2);
    const { api, session, fetchFn, changed } = accountSetup(other);

    const { response } = await api.PATCH("/api/users/me", { body: { display_name: "Ana" } });

    expect(response.status).toBe(401);
    expect(fetchFn).toHaveBeenCalledOnce();
    expect(changed).toHaveBeenCalledOnce();
    expect(session.getToken()).toBe(other);
  });

  it("retries as usual when the refresh returns the same user", async () => {
    const { api, fetchFn, changed } = accountSetup(jwt("user-x", 2));

    const { response } = await api.GET("/api/users/me");

    expect(response.status).toBe(200);
    expect(fetchFn).toHaveBeenCalledTimes(2);
    expect(changed).not.toHaveBeenCalled();
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

/** An access token for `sub`, as far as the session reads it (the server verifies it). */
const tokenFor = (sub: string, n = 1) => `h.${btoa(JSON.stringify({ sub, n }))}.s`;

describe("several accounts", () => {
  function accountsWorld() {
    const storage = memoryStorage();
    const calls: (string | null)[] = [];
    const listeners = new Set<(key: string | null) => void>();
    let n = 0;
    const refreshRequest: SessionDeps["refreshRequest"] = async (_signal, account) => {
      calls.push(account);
      n += 1;
      return account === "gone" ? null : tokenFor(account ?? "only", n);
    };
    const tab = () =>
      createSession({
        refreshRequest,
        storage: () => storage,
        sleep: yieldToOthers,
        onStorage: (listener) => {
          listeners.add(listener);
          return () => listeners.delete(listener);
        },
      });
    // What the browser does for the other tabs when one writes to localStorage.
    const broadcast = (key: string) => listeners.forEach((listener) => listener(key));
    return { storage, calls, tab, broadcast };
  }

  it("remembers the account signed in to, and refreshes that one", async () => {
    const { storage, calls, tab } = accountsWorld();
    const session = tab();
    session.setToken(tokenFor("alice"));
    session.clear(); // A reload: the token is gone, the choice of account isn't.

    await session.refresh();

    expect(storage.items.get("auth.account")).toBe("alice");
    expect(calls).toEqual(["alice"]);
    expect(session.getAccount()).toBe("alice");
  });

  it("switches to another account and tells the page", async () => {
    const { storage, calls, tab } = accountsWorld();
    const session = tab();
    session.setToken(tokenFor("alice"));
    const changed = vi.fn();
    session.onAccountChanged(changed);

    const token = await session.switchTo("bob");

    expect(token).toBe(tokenFor("bob", 1));
    expect(calls).toEqual(["bob"]);
    expect(storage.items.get("auth.account")).toBe("bob");
    expect(changed).toHaveBeenCalledOnce();
  });

  it("has no token when the account switched to is signed out", async () => {
    const { tab } = accountsWorld();
    const session = tab();
    session.setToken(tokenFor("alice"));

    expect(await session.switchTo("gone")).toBeNull();
    expect(session.getToken()).toBeNull();
  });

  it("makes the other tabs follow a switch", async () => {
    const { tab, broadcast } = accountsWorld();
    const [first, second] = [tab(), tab()];
    first.setToken(tokenFor("alice"));
    second.setToken(tokenFor("alice"));
    const changed = vi.fn();
    second.onAccountChanged(changed);

    await first.switchTo("bob");
    broadcast("auth.account");
    await vi.waitFor(() => expect(changed).toHaveBeenCalled());

    expect(second.getAccount()).toBe("bob");
  });

  it("ignores other keys and a switch to the account already in use", async () => {
    const { calls, tab, broadcast, storage } = accountsWorld();
    const session = tab();
    session.setToken(tokenFor("alice"));

    broadcast("auth.refresh.lease");
    storage.setItem("auth.account", "alice");
    broadcast("auth.account");
    await yieldToOthers();

    expect(calls).toEqual([]);
  });

  it("forgets the account after signing out of it", () => {
    const { storage, tab } = accountsWorld();
    const session = tab();
    session.setToken(tokenFor("alice"));

    session.clear();
    session.forgetAccount();

    expect(storage.items.has("auth.account")).toBe(false);
    expect(session.getAccount()).toBeNull();
  });
});

describe("requestRefresh", () => {
  it("names the account to refresh", async () => {
    const fetchFn = vi.fn(
      async (_request: Request) =>
        new Response('{"access_token":"t","token_type":"bearer","expires_in":900}', {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );

    await requestRefresh(createApi("http://test", fetchFn), new AbortController().signal, "a1");

    expect(await fetchFn.mock.calls[0]![0].json()).toEqual({ user_id: "a1" });
  });

  it("reads 'which account?' as no session, not a failure", async () => {
    const fetchFn = async () =>
      new Response('{"detail":"say which one"}', {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });

    const result = await requestRefresh(
      createApi("http://test", fetchFn),
      new AbortController().signal,
    );

    expect(result).toBeNull();
  });
});

describe("several accounts, across tabs and failures", () => {
  function tabs(refresh: SessionDeps["refreshRequest"]) {
    const storage = memoryStorage();
    const listeners = new Set<(key: string | null) => void>();
    const tab = () =>
      createSession({
        refreshRequest: refresh,
        storage: () => storage,
        sleep: yieldToOthers,
        onStorage: (listener) => {
          listeners.add(listener);
          return () => listeners.delete(listener);
        },
      });
    const broadcast = () => listeners.forEach((listener) => listener("auth.account"));
    return { storage, tab, broadcast };
  }

  it("signs the other tabs out of an account signed out of in one", async () => {
    const { tab, broadcast } = tabs(async (_s, account) => tokenFor(account ?? "x"));
    const [first, second] = [tab(), tab()];
    first.setToken(tokenFor("alice"));
    second.setToken(tokenFor("alice"));
    const lost = vi.fn();
    second.onLost(lost);

    first.clear();
    first.forgetAccount();
    broadcast();

    expect(second.getToken()).toBeNull();
    expect(lost).toHaveBeenCalledOnce();
  });

  it("follows another tab without writing the choice back", async () => {
    const { storage, tab, broadcast } = tabs(async (_s, account) => tokenFor(account ?? "x"));
    const second = tab();
    second.setToken(tokenFor("alice"));
    const writes = vi.spyOn(storage, "setItem");

    storage.items.set("auth.account", "bob"); // Written by the first tab.
    broadcast();
    await vi.waitFor(() => expect(second.getAccount()).toBe("bob"));

    expect(writes.mock.calls.filter(([key]) => key === "auth.account")).toEqual([]);
  });

  it("follows what's in storage now, not an older event", async () => {
    const calls: (string | null)[] = [];
    const { storage, tab, broadcast } = tabs(async (_s, account) => {
      calls.push(account);
      return tokenFor(account ?? "x");
    });
    const session = tab();
    session.setToken(tokenFor("carol"));

    storage.items.set("auth.account", "carol"); // bob was chosen, then carol: carol is current.
    broadcast();
    await yieldToOthers();

    expect(calls).toEqual([]);
  });

  it("a refresh doesn't undo another tab's switch", async () => {
    const { storage, tab } = tabs(async (_s, account) => tokenFor(account ?? "x"));
    const session = tab();
    session.setToken(tokenFor("alice"));
    storage.items.set("auth.account", "bob"); // Another tab switched meanwhile.

    await session.refresh();

    expect(storage.items.get("auth.account")).toBe("bob");
  });

  it("tells a server that couldn't answer from a session that ended, and tries again", async () => {
    let fail = true;
    const { tab } = tabs(async (_s, account) => {
      if (fail) throw new Error("502");
      return tokenFor(account ?? "x");
    });
    const session = tab();

    await session.restore();
    expect(session.lastOutcome()).toBe("unavailable");

    fail = false;
    await session.restore();
    expect(session.getToken()).not.toBeNull();
    expect(session.lastOutcome()).toBe("ok");
  });

  it("says when the session was refused", async () => {
    const { tab } = tabs(async () => null);
    const session = tab();

    await session.restore();

    expect(session.lastOutcome()).toBe("refused");
  });
});
