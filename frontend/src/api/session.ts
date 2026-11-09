/** The signed-in session. The access token lives only in this module's memory. */

const LEASE_KEY = "auth.refresh.lease";
/** Longer than a refresh can last, so a live holder never loses its lease. */
const LEASE_MS = 10_000;
const REFRESH_TIMEOUT_MS = 8_000;
const MAX_LEASE_WAIT_MS = 3 * LEASE_MS;
/** Two tabs can write at once. The one whose write survives this pause holds the lease. */
const SETTLE_MS = 60;
const POLL_MS = 100;

type LeaseStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export interface SessionDeps {
  /** Returns a new access token, or null if the refresh cookie was refused. Throws if the
   * server couldn't give an answer, which says nothing about the session. */
  refreshRequest: (signal: AbortSignal) => Promise<string | null>;
  /** A function, because merely reading window.localStorage can throw. */
  storage: () => LeaseStorage;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
}

export interface Session {
  getToken: () => string | null;
  setToken: (token: string) => void;
  clear: () => void;
  /** Brings back the session after a page load, once. Skipped if already signed in. */
  restore: () => Promise<void>;
  /** Rotates the refresh cookie. Concurrent calls share one request. */
  refresh: () => Promise<string | null>;
  /** A token to replace `usedToken`, refreshing only if nobody has replaced it already. */
  replace: (usedToken: string) => Promise<string | null>;
  /** Calls `listener` when a signed-in session ends without the user asking. */
  onLost: (listener: () => void) => () => void;
}

interface Lease {
  id: string;
  expires: number;
}

function readLease(storage: LeaseStorage): Lease | null {
  try {
    return JSON.parse(storage.getItem(LEASE_KEY) ?? "null") as Lease | null;
  } catch {
    return null; // Corrupt, so nobody can be relying on it.
  }
}

export function createSession(deps: SessionDeps): Session {
  const now = deps.now ?? Date.now;
  const sleep = deps.sleep ?? ((ms) => new Promise<void>((done) => setTimeout(done, ms)));
  const listeners = new Set<() => void>();
  let token: string | null = null;
  let inFlight: Promise<string | null> | null = null;
  let restored: Promise<unknown> | null = null;
  // Bumped by login and logout, so a refresh that started earlier can't overwrite them.
  let epoch = 0;

  /**
   * The server treats a second use of a refresh token as theft and ends the session, so two
   * tabs must never refresh at once. localStorage, because navigator.locks doesn't exist on
   * plain HTTP, which is how the default deployment runs. Returns the release function, or
   * null if the lease couldn't be had in time.
   */
  async function acquireLease(): Promise<(() => void) | null> {
    const noLease = () => {};
    try {
      const storage = deps.storage();
      const id = crypto.getRandomValues(new Uint32Array(2)).join("-");
      const deadline = now() + MAX_LEASE_WAIT_MS;
      while (now() < deadline) {
        const lease = readLease(storage);
        if (lease && lease.expires > now()) {
          await sleep(POLL_MS);
          continue;
        }
        storage.setItem(LEASE_KEY, JSON.stringify({ id, expires: now() + LEASE_MS }));
        await sleep(SETTLE_MS);
        if (readLease(storage)?.id === id) {
          return () => {
            if (readLease(storage)?.id === id) storage.removeItem(LEASE_KEY);
          };
        }
      }
      return null;
    } catch {
      return noLease; // No storage at all, so no other tab can be coordinated with either.
    }
  }

  async function runRefresh(): Promise<string | null> {
    const startedAt = epoch;
    const hadToken = token !== null;
    const release = await acquireLease();
    if (!release) return null;
    let fresh: string | null;
    try {
      fresh = await deps.refreshRequest(AbortSignal.timeout(REFRESH_TIMEOUT_MS));
    } catch {
      return null; // A temporary failure: the cookie is still good, so keep the session.
    } finally {
      release();
    }
    if (epoch !== startedAt) return token;
    token = fresh;
    if (fresh === null && hadToken) listeners.forEach((listener) => listener());
    return fresh;
  }

  function refresh(): Promise<string | null> {
    inFlight ??= runRefresh().finally(() => {
      inFlight = null;
    });
    return inFlight;
  }

  return {
    getToken: () => token,
    setToken(next) {
      epoch += 1;
      token = next;
    },
    clear() {
      epoch += 1;
      token = null;
    },
    async restore() {
      restored ??= token === null ? refresh() : Promise.resolve();
      await restored;
    },
    refresh,
    replace: async (usedToken) => (token !== null && token !== usedToken ? token : refresh()),
    onLost(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
