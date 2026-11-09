import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";

type OwnerPage = components["schemas"]["VideoOwnerPage"];

export const MY_VIDEOS_KEY = ["my-videos"];
const POLL_MS = 3000;

/** Only `processing` changes without this page doing anything. An abandoned `uploading` video
 * stays that way for up to a day, and polling for it would achieve nothing. */
export function needsPolling(pages: Pick<OwnerPage, "items">[] | undefined): boolean {
  return pages?.some((page) => page.items.some((video) => video.status === "processing")) ?? false;
}

export function useMyVideos() {
  return useInfiniteQuery({
    queryKey: MY_VIDEOS_KEY,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) => {
      const { data, error } = await api.GET("/api/users/me/videos", {
        params: { query: { cursor: pageParam } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: (query) => (needsPolling(query.state.data?.pages) ? POLL_MS : false),
  });
}

export function useDeleteVideo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (videoId: string) => {
      const { response, error } = await api.DELETE("/api/videos/{video_id}", {
        params: { path: { video_id: videoId } },
      });
      if (!response.ok) throw new Error(errorMessage(error));
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: MY_VIDEOS_KEY }),
  });
}
