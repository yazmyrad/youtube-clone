import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";
import { useAuth } from "./useAuth";

export type VideoDetails = components["schemas"]["VideoDetailsOut"];
type VideoStatus = VideoDetails["status"];

const POLL_MS = 3000;

/** The account is part of the key: signing out removes a cached entry without refetching it,
 * and the page would go on showing that account's reaction, or its private video. */
export function videoKey(videoId: string, username: string | null) {
  return ["video", videoId, username];
}

/** 404 for no access or no such video, 422 for an id that can't be one. */
export class VideoNotFound extends Error {}

export function statusMessage(status: VideoStatus): string | null {
  switch (status) {
    case "uploading":
      return "This video's upload hasn't finished.";
    case "processing":
      return "This video is still processing. It will play here when it's ready.";
    case "failed":
      return "This video couldn't be processed.";
    case "ready":
      return null;
  }
}

export function useVideo(videoId: string) {
  const { user, isLoading } = useAuth();
  return useQuery({
    queryKey: videoKey(videoId, user?.username ?? null),
    // Otherwise the answer for a signed-out visitor is fetched first, and thrown away.
    enabled: !isLoading,
    queryFn: async ({ signal }) => {
      const { data, error, response } = await api.GET("/api/videos/{video_id}", {
        params: { path: { video_id: videoId } },
        signal,
      });
      if (data) return data;
      if (response.status === 404 || response.status === 422) throw new VideoNotFound();
      throw new Error(errorMessage(error));
    },
    retry: (failures, failure) => !(failure instanceof VideoNotFound) && failures < 1,
    refetchInterval: (query) => (query.state.data?.status === "processing" ? POLL_MS : false),
  });
}
