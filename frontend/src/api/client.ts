import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";
import { createSession, type Session } from "./session";

type FetchFn = (request: Request) => Promise<Response>;

const browserFetch: FetchFn = (request) => fetch(request);

export function createApi(baseUrl = "", fetchFn: FetchFn = browserFetch) {
  return createClient<paths>({ baseUrl, fetch: fetchFn });
}

export type Api = ReturnType<typeof createApi>;

// The refresh cookie authenticates these. A 401 from them is the answer, not an expired token.
const isAuthRoute = (request: Request) => new URL(request.url).pathname.startsWith("/api/auth/");

/** Sends the access token. On a 401, replaces the token and retries the request once. */
export function authMiddleware(session: Session, fetchFn: FetchFn = browserFetch): Middleware {
  const replayable = new WeakMap<Request, Request>();
  const sentTokens = new WeakMap<Request, string>();

  return {
    onRequest({ request }) {
      const token = session.getToken();
      if (token === null || isAuthRoute(request)) return undefined;
      request.headers.set("Authorization", `Bearer ${token}`);
      sentTokens.set(request, token);
      // Sending a request uses up its body, so the retry needs a copy made beforehand.
      replayable.set(request, request.clone());
      return request;
    },
    async onResponse({ request, response }) {
      const sentToken = sentTokens.get(request);
      const retry = replayable.get(request);
      if (response.status !== 401 || sentToken === undefined || retry === undefined) {
        return undefined;
      }
      const token = await session.replace(sentToken);
      if (token === null) return undefined;
      retry.headers.set("Authorization", `Bearer ${token}`);
      return fetchFn(retry);
    },
  };
}

/** Only a 401 means the session is over. Anything else is the server failing to answer. */
export async function requestRefresh(client: Api, signal: AbortSignal): Promise<string | null> {
  const { data, response } = await client.POST("/api/auth/refresh", { signal });
  if (data) return data.access_token;
  if (response.status === 401) return null;
  throw new Error(`Refresh failed (${response.status})`);
}

const unauthenticated = createApi();

export const session = createSession({
  storage: () => window.localStorage,
  refreshRequest: (signal) => requestRefresh(unauthenticated, signal),
});

export const api = createApi();
api.use(authMiddleware(session));

/** For login, register and logout, which never carry the access token. */
export const authApi = unauthenticated;
