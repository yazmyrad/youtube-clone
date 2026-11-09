import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Api } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";
import { useAuth } from "./useAuth";
import { videoKey, type VideoDetails } from "./useVideo";

export type Reaction = components["schemas"]["ReactionType"];
type ReactionState = components["schemas"]["ReactionStateOut"];

/** Pressing the active button takes the reaction back. */
export function nextReaction(current: Reaction | null, pressed: Reaction): Reaction | null {
  return current === pressed ? null : pressed;
}

export function withReactionState(video: VideoDetails, state: ReactionState): VideoDetails {
  return { ...video, ...state };
}

export async function sendReaction(
  client: Api,
  videoId: string,
  reaction: Reaction | null,
): Promise<ReactionState> {
  const params = { path: { video_id: videoId } };
  const { data, error } = reaction
    ? await client.PUT("/api/videos/{video_id}/reaction", { params, body: { reaction } })
    : await client.DELETE("/api/videos/{video_id}/reaction", { params });
  if (!data) throw new Error(errorMessage(error));
  return data;
}

export function useReaction(videoId: string) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reaction: Reaction | null) => sendReaction(api, videoId, reaction),
    onSuccess: (state) => {
      queryClient.setQueryData<VideoDetails>(
        videoKey(videoId, user?.username ?? null),
        (video) => video && withReactionState(video, state),
      );
    },
  });
}
