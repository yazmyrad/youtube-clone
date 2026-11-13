import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Api } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";
import { useAuth } from "./useAuth";

export type AdminUser = components["schemas"]["AdminUserOut"];
export type UserChange = components["schemas"]["AdminUserUpdateIn"];

const ADMIN_USERS_KEY = "admin-users";

export function useAdminUsers(q: string) {
  const { user } = useAuth();
  return useInfiniteQuery({
    queryKey: [ADMIN_USERS_KEY, user?.username ?? null, q],
    enabled: user?.role === "admin",
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) => {
      const { data, error } = await api.GET("/api/admin/users", {
        params: { query: { q: q || undefined, cursor: pageParam } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

export async function changeUser(
  client: Api,
  userId: string,
  change: UserChange,
): Promise<AdminUser> {
  const { data, error } = await client.PATCH("/api/admin/users/{user_id}", {
    params: { path: { user_id: userId } },
    body: change,
  });
  if (!data) throw new Error(errorMessage(error));
  return data;
}

export function useChangeUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, change }: { userId: string; change: UserChange }) =>
      changeUser(api, userId, change),
    onSettled: () => queryClient.invalidateQueries({ queryKey: [ADMIN_USERS_KEY] }),
  });
}
