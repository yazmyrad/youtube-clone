import { describe, expect, it, vi } from "vitest";

import { signOut } from "./account";
import { createApi } from "./client";
import { createSession } from "./session";

function signedIn() {
  const session = createSession({ refreshRequest: async () => null, storage: () => { throw new Error("unused"); } });
  session.setToken("token");
  return session;
}

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
