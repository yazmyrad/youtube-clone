import { useInfiniteQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";
import { useAuth } from "./useAuth";

export type ShortCardData = components["schemas"]["VideoCardOut"];

/** Public Shorts, newest first: the shelf on home and the Shorts player's queue. */
export function useShortsFeed() {
  return useInfiniteQuery({
    queryKey: ["feed", "shorts"],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) => {
      const { data, error } = await api.GET("/api/videos/shorts", {
        params: { query: { cursor: pageParam } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

/** A channel's Shorts tab; the owner's private ones too. */
export function useChannelShorts(username: string) {
  const { user, isLoading } = useAuth();
  return useInfiniteQuery({
    queryKey: ["channel", username.toLowerCase(), user?.username ?? null, "shorts"],
    enabled: !isLoading,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) => {
      const { data, error } = await api.GET("/api/channels/{username}/shorts", {
        params: { path: { username }, query: { cursor: pageParam } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}
