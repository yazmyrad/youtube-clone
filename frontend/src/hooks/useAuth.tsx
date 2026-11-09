import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";

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
  logout: () => Promise<void>;
}

const ME_KEY = ["me"];
const AuthContext = createContext<Auth | null>(null);

// Once per page load, outside React: StrictMode runs effects twice, and a second refresh
// from one page load must not happen.
let restored: Promise<unknown> | undefined;
const restoreSession = () => (restored ??= session.refresh());

async function fetchMe(): Promise<Me | null> {
  await restoreSession();
  if (session.getToken() === null) return null;
  const { data, response } = await api.GET("/api/users/me");
  if (response.status === 401) return null;
  if (!data) throw new Error(`Could not load your account (${response.status})`);
  return data;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: ME_KEY,
    queryFn: fetchMe,
    staleTime: 5 * 60_000,
  });

  const value = useMemo<Auth>(() => {
    // One account's data must not be shown to the next. Not queryClient.clear(), which
    // would leave this provider watching a query that's no longer in the cache.
    const dropAccountData = () =>
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] });

    async function login(credentials: LoginIn) {
      const { data: tokens, error } = await authApi.POST("/api/auth/login", { body: credentials });
      if (!tokens) throw new Error(errorMessage(error));
      session.setToken(tokens.access_token);
      dropAccountData();
      await queryClient.invalidateQueries({ queryKey: ME_KEY });
    }

    return {
      user: data ?? null,
      isLoading: isPending,
      login,
      async register(account) {
        const { data: created, error } = await authApi.POST("/api/auth/register", {
          body: account,
        });
        if (!created) throw new Error(errorMessage(error));
        await login({ email: account.email, password: account.password });
      },
      async logout() {
        try {
          await authApi.POST("/api/auth/logout");
        } finally {
          session.clear();
          dropAccountData();
          queryClient.setQueryData(ME_KEY, null);
        }
      },
    };
  }, [data, isPending, queryClient]);

  useEffect(
    () =>
      session.onLost(() => {
        queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] });
        queryClient.setQueryData(ME_KEY, null);
      }),
    [queryClient],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside AuthProvider");
  return auth;
}
