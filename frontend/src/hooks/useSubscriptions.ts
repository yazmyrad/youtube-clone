import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";
import { useAuth } from "./useAuth";

export type SubscribedChannel = components["schemas"]["SubscribedChannelOut"];

/** As many as the sidebar lists. */
export const SIDEBAR_CHANNELS = 50;

/** Everything under this key changes when the account subscribes or unsubscribes. */
export const SUBSCRIPTIONS_KEY = "subscriptions";

/** The channels the signed-in account subscribes to, most recent first. */
export function useMySubscriptions() {
  const { user } = useAuth();
  return useQuery({
    queryKey: [SUBSCRIPTIONS_KEY, "channels", user?.username ?? null],
    enabled: user !== null,
    queryFn: async ({ signal }) => {
      const { data, error } = await api.GET("/api/users/me/subscriptions", {
        params: { query: { limit: SIDEBAR_CHANNELS } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data.items;
    },
  });
}

/** Latest videos from subscribed channels. */
export function useSubscriptionFeed() {
  const { user } = useAuth();
  return useInfiniteQuery({
    queryKey: [SUBSCRIPTIONS_KEY, "feed", user?.username ?? null],
    enabled: user !== null,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) => {
      const { data, error } = await api.GET("/api/feed/subscriptions", {
        params: { query: { cursor: pageParam } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}
