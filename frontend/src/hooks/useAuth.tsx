import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";

import { listAccounts, registerAndSignIn, signOut } from "../api/account";
import { api, authApi, session } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";

export type Me = components["schemas"]["MeOut"];
type LoginIn = components["schemas"]["LoginIn"];
type RegisterIn = components["schemas"]["RegisterIn"];

interface Auth {
  user: Me | null;
  isLoading: boolean;
  login: (credentials: LoginIn) => Promise<void>;
  register: (account: RegisterIn) => Promise<void>;
  /** Signs out of the account in use; the next signed-in one, if any, takes over. */
  logout: () => Promise<void>;
  /** Signs out of every account in this browser. */
  logoutAll: () => Promise<void>;
  /** Uses another of the browser's signed-in accounts. */
  switchAccount: (accountId: string) => Promise<void>;
}

export const ACCOUNTS_KEY = ["accounts"];

export const ME_KEY = ["me"];
const AuthContext = createContext<Auth | null>(null);

// One account's data must not be shown to the next. Not queryClient.clear(), which would
// leave AuthProvider watching a query that's no longer in the cache.
function dropAccountData(queryClient: QueryClient) {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] });
}

async function fetchMe(): Promise<Me | null> {
  await session.restore();
  if (session.getToken() === null) {
    // The account in use was signed out (here or in another tab), or none was chosen yet:
    // carry on as another account still signed in in this browser, as YouTube does.
    const next = (await listAccounts(authApi).catch(() => []))[0];
    if (!next || (await session.switchTo(next.id)) === null) return null;
  }
  const { data, response } = await api.GET("/api/users/me");
  if (data) return data;
  // A token that's still held means the refresh failed for now. Throwing keeps the last result.
  if (session.getToken() === null) return null;
  throw new Error(`Could not load your account (${response.status})`);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: ME_KEY,
    queryFn: fetchMe,
    staleTime: 5 * 60_000,
  });

  const value = useMemo<Auth>(() => {
    async function login(credentials: LoginIn) {
      const { data: tokens, error } = await authApi.POST("/api/auth/login", { body: credentials });
      if (!tokens) throw new Error(errorMessage(error));
      session.setToken(tokens.access_token);
      dropAccountData(queryClient);
      await queryClient.invalidateQueries({ queryKey: ME_KEY });
    }

    return {
      user: data ?? null,
      isLoading: isPending,
      login,
      register: (account) => registerAndSignIn(authApi, account, login),
      async logout() {
        await signOut(authApi, session);
        dropAccountData(queryClient);
        if (session.getToken() === null) queryClient.setQueryData(ME_KEY, null);
        else await queryClient.invalidateQueries({ queryKey: ME_KEY });
      },
      async logoutAll() {
        await signOut(authApi, session, true);
        dropAccountData(queryClient);
        queryClient.setQueryData(ME_KEY, null);
      },
      async switchAccount(accountId) {
        if (accountId === data?.id) return;
        const token = await session.switchTo(accountId);
        dropAccountData(queryClient);
        if (token === null) throw new Error("That account is signed out. Please sign in again.");
        await queryClient.invalidateQueries({ queryKey: ME_KEY });
      },
    };
  }, [data, isPending, queryClient]);

  useEffect(() => {
    const stopLost = session.onLost(() => {
      dropAccountData(queryClient);
      queryClient.setQueryData(ME_KEY, null);
    });
    const stopChanged = session.onAccountChanged(() => {
      dropAccountData(queryClient);
      void queryClient.invalidateQueries({ queryKey: ME_KEY });
    });
    return () => {
      stopLost();
      stopChanged();
    };
  }, [queryClient]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside AuthProvider");
  return auth;
}
