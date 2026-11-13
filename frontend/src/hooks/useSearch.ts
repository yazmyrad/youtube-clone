import { useInfiniteQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { errorMessage } from "../api/errors";

// The API's limits for `q`, after it strips whitespace.
export const MIN_QUERY = 2;
export const MAX_QUERY = 100;

/** The text to search for, or null when the API would reject it. */
export function searchText(raw: string | null): string | null {
  const text = raw?.trim() ?? "";
  return text.length >= MIN_QUERY && text.length <= MAX_QUERY ? text : null;
}

export function useSearch(text: string | null) {
  return useInfiniteQuery({
    queryKey: ["search", text],
    enabled: text !== null,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) => {
      const { data, error } = await api.GET("/api/search/videos", {
        params: { query: { q: text!, cursor: pageParam } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}
