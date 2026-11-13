import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import { errorMessage } from "../api/errors";
import { useAuth } from "./useAuth";

export const HISTORY_KEY = "history";

export function useHistory() {
  const { user } = useAuth();
  return useInfiniteQuery({
    queryKey: [HISTORY_KEY, user?.username ?? null],
    enabled: user !== null,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) => {
      const { data, error } = await api.GET("/api/users/me/history", {
        params: { query: { cursor: pageParam } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

/** Removes one video from the history, or all of them when `videoId` is null. */
export function useForget() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (videoId: string | null) => {
      const { error, response } = videoId
        ? await api.DELETE("/api/users/me/history/{video_id}", {
            params: { path: { video_id: videoId } },
          })
        : await api.DELETE("/api/users/me/history");
      if (!response.ok) throw new Error(errorMessage(error));
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: [HISTORY_KEY] }),
  });
}
