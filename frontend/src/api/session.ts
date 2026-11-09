/** The signed-in session. The access token lives only in this module's memory. */

const LEASE_KEY = "auth.refresh.lease";
/** How long a closed tab can block the others. A live holder keeps renewing its lease. */
const LEASE_MS = 10_000;
const LEASE_RENEW_MS = 3_000;
/** After nginx's own 60 s limit. Giving up first would lose a rotated cookie still on its
 * way, and the next refresh would look like token theft and end the session. */
const REFRESH_TIMEOUT_MS = 65_000;
const MAX_LEASE_WAIT_MS = REFRESH_TIMEOUT_MS + LEASE_MS;
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
  /** A token to replace `usedToken`, refreshing only if nobody has replaced it already.
   * Null if there's none, or if it belongs to someone else. */
  replace: (usedToken: string) => Promise<string | null>;
  /** Calls `listener` when a signed-in session ends without the user asking. */
  onLost: (listener: () => void) => () => void;
  /** Calls `listener` when a refresh comes back as another user, after a login in another tab. */
  onAccountChanged: (listener: () => void) => () => void;
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

/** The user a token belongs to. Not verified, which is the server's job on every request. */
function subjectOf(accessToken: string): string | null {
  try {
    const payload = accessToken.split(".")[1]!.replace(/-/g, "+").replace(/_/g, "/");
    return (JSON.parse(atob(payload)) as { sub?: string }).sub ?? null;
  } catch {
    return null;
  }
}

export function createSession(deps: SessionDeps): Session {
  const now = deps.now ?? Date.now;
  const sleep = deps.sleep ?? ((ms) => new Promise<void>((done) => setTimeout(done, ms)));
  const lostListeners = new Set<() => void>();
  const accountListeners = new Set<() => void>();
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
          const write = () => {
            storage.setItem(LEASE_KEY, JSON.stringify({ id, expires: now() + LEASE_MS }));
          };
          const renewal = setInterval(() => {
            try {
              if (readLease(storage)?.id === id) write();
            } catch {
              // Storage went away. The lease just runs out.
            }
          }, LEASE_RENEW_MS);
          return () => {
            clearInterval(renewal);
            try {
              if (readLease(storage)?.id === id) storage.removeItem(LEASE_KEY);
            } catch {
              // As above.
            }
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
    const previous = token;
    const release = await acquireLease();
    if (!release) return null;
    let fresh: string | null;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REFRESH_TIMEOUT_MS);
    try {
      fresh = await deps.refreshRequest(controller.signal);
    } catch {
      return null; // A temporary failure: the cookie is still good, so keep the session.
    } finally {
      clearTimeout(timeout);
      release();
    }
    if (epoch !== startedAt) return token;
    token = fresh;
    if (previous !== null) {
      if (fresh === null) lostListeners.forEach((listener) => listener());
      else if (subjectOf(fresh) !== subjectOf(previous)) {
        accountListeners.forEach((listener) => listener());
      }
    }
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
    async replace(usedToken) {
      const next = token !== null && token !== usedToken ? token : await refresh();
      return next !== null && subjectOf(next) === subjectOf(usedToken) ? next : null;
    },
    onLost(listener) {
      lostListeners.add(listener);
      return () => lostListeners.delete(listener);
    },
    onAccountChanged(listener) {
      accountListeners.add(listener);
      return () => accountListeners.delete(listener);
    },
  };
}
