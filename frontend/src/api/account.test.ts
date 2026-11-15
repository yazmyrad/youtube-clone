import { describe, expect, it, vi } from "vitest";

import { registerAndSignIn, signOut } from "./account";
import { createApi } from "./client";
import { createSession } from "./session";

function signedIn() {
  const session = createSession({ refreshRequest: async () => null, storage: () => { throw new Error("unused"); } });
  session.setToken("token");
  return session;
}

describe("registerAndSignIn", () => {
  const account = {
    username: "ana",
    email: "ana@example.com",
    password: "correct horse",
    display_name: "Ana",
  };
  const respond = (status: number, body: string) =>
    vi.fn(
      async () => new Response(body, { status, headers: { "Content-Type": "application/json" } }),
    );

  it("signs in with the new account's credentials", async () => {
    const fetchFn = respond(201, '{"id":"1"}');
    const login = vi.fn(async () => {});

    await registerAndSignIn(createApi("http://test", fetchFn), account, login);

    expect(login).toHaveBeenCalledWith({ email: account.email, password: account.password });
  });

  it("says the account exists when only the sign-in failed", async () => {
    const fetchFn = respond(201, '{"id":"1"}');
    const login = vi.fn(() => Promise.reject(new Error("Service unavailable")));

    await expect(
      registerAndSignIn(createApi("http://test", fetchFn), account, login),
    ).rejects.toThrow("Your account was created");

    expect(fetchFn).toHaveBeenCalledOnce();
  });

  it("shows the server's reason when registering failed, without signing in", async () => {
    const fetchFn = respond(409, '{"detail":"Username is taken"}');
    const login = vi.fn(async () => {});

    await expect(
      registerAndSignIn(createApi("http://test", fetchFn), account, login),
    ).rejects.toThrow("Username is taken");

    expect(login).not.toHaveBeenCalled();
  });
});

describe("signOut", () => {
  it("ends the session once the server has revoked it", async () => {
    const session = signedIn();
    const client = createApi("http://test", async () => new Response(null, { status: 204 }));

    await signOut(client, session);

    expect(session.getToken()).toBeNull();
  });

  it("keeps the session when the server refuses", async () => {
    const session = signedIn();
    const client = createApi("http://test", async () => new Response("{}", { status: 500 }));

    await expect(signOut(client, session)).rejects.toThrow("Couldn't sign out");

    expect(session.getToken()).toBe("token");
  });

  it("keeps the session when the server can't be reached", async () => {
    const session = signedIn();
    const offline = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));

    await expect(signOut(createApi("http://test", offline), session)).rejects.toThrow();

    expect(session.getToken()).toBe("token");
  });
});

describe("signing out with several accounts", () => {
  const tokenFor = (sub: string) => `h.${btoa(JSON.stringify({ sub }))}.s`;

  function browser(remaining: { id: string }[]) {
    const items = new Map<string, string>();
    const storage = {
      getItem: (key: string) => items.get(key) ?? null,
      setItem: (key: string, value: string) => void items.set(key, value),
      removeItem: (key: string) => void items.delete(key),
    };
    const refreshed: (string | null)[] = [];
    const session = createSession({
      refreshRequest: async (_signal, account) => {
        refreshed.push(account);
        return account ? tokenFor(account) : null;
      },
      storage: () => storage,
      sleep: async () => {},
    });
    session.setToken(tokenFor("alice"));
    const requests: Request[] = [];
    const client = createApi("http://test", async (request) => {
      requests.push(request);
      if (request.url.endsWith("/api/auth/accounts")) {
        return new Response(JSON.stringify({ items: remaining }), {
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(null, { status: 204 });
    });
    return { session, client, requests, refreshed };
  }

  it("signs out of the account in use only, and carries on as the next one", async () => {
    const { session, client, requests, refreshed } = browser([{ id: "bob" }]);

    await signOut(client, session);

    expect(await requests[0]!.json()).toEqual({ user_id: "alice" });
    expect(refreshed).toEqual(["bob"]);
    expect(session.getAccount()).toBe("bob");
  });

  it("is signed out when no other account is left", async () => {
    const { session, client } = browser([]);

    await signOut(client, session);

    expect(session.getToken()).toBeNull();
    expect(session.getAccount()).toBeNull();
  });

  it("signs out of every account at once", async () => {
    const { session, client, requests } = browser([{ id: "bob" }]);

    await signOut(client, session, true);

    expect(requests).toHaveLength(1);
    expect(await requests[0]!.text()).toBe("");
    expect(session.getToken()).toBeNull();
  });
});
