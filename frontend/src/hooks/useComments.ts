import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Api } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";
import { useAuth } from "./useAuth";
import { videoKey } from "./useVideo";

export type Comment = components["schemas"]["CommentOut"];
type CommentPage = components["schemas"]["CommentPage"];

/** Counted in UTF-16 units by a textarea and in code points by the API, so this is never over. */
export const MAX_COMMENT_LENGTH = 2000;

const commentsKey = (videoId: string) => ["comments", videoId];

/** What to send, or null if there's nothing worth sending. */
export function cleanComment(text: string): string | null {
  const body = text.trim();
  return body === "" ? null : body;
}

export async function fetchComments(
  client: Api,
  videoId: string,
  cursor: string | undefined,
  signal?: AbortSignal,
): Promise<CommentPage> {
  const { data, error } = await client.GET("/api/videos/{video_id}/comments", {
    params: { path: { video_id: videoId }, query: { cursor } },
    signal,
  });
  if (!data) throw new Error(errorMessage(error));
  return data;
}

export async function postComment(client: Api, videoId: string, body: string): Promise<Comment> {
  const { data, error } = await client.POST("/api/videos/{video_id}/comments", {
    params: { path: { video_id: videoId } },
    body: { body },
  });
  if (!data) throw new Error(errorMessage(error));
  return data;
}

export function useComments(videoId: string) {
  return useInfiniteQuery({
    queryKey: commentsKey(videoId),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => fetchComments(api, videoId, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

export function useAddComment(videoId: string) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => postComment(api, videoId, body),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: commentsKey(videoId) }),
        queryClient.invalidateQueries({ queryKey: videoKey(videoId, user?.username ?? null) }),
      ]),
  });
}
