import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { errorMessage } from "../api/errors";

export function useFeed() {
  return useInfiniteQuery({
    queryKey: ["feed"],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) => {
      const { data, error } = await api.GET("/api/videos", {
        params: { query: { cursor: pageParam } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

/** The feed's first page alone, for side lists like Up next. Its own key, so it never makes
 * the home page's pages reload, nor they it. */
export function useFeedFirstPage() {
  return useQuery({
    queryKey: ["feed", "first-page"],
    queryFn: async ({ signal }) => {
      const { data, error } = await api.GET("/api/videos", {
        params: { query: { cursor: undefined } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data.items;
    },
  });
}
