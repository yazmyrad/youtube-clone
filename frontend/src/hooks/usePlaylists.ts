import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Api } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";
import { useAuth } from "./useAuth";

export type Playlist = components["schemas"]["PlaylistOut"];
export type PlaylistSummary = components["schemas"]["PlaylistSummaryOut"];

/** 404 for no access or no such playlist, 422 for an id that can't be one. */
export class PlaylistNotFound extends Error {}

/** Everything about playlists. A change to one may change any list that shows it. */
export const PLAYLISTS_KEY = "playlists";

/** The account is part of the key: what a playlist shows depends on who is looking. */
export function playlistKey(playlistId: string, viewer: string | null) {
  return [PLAYLISTS_KEY, "one", playlistId, viewer];
}

/** Off while `playlistId` is null, for the watch page outside a playlist. */
export function usePlaylist(playlistId: string | null) {
  const { user, isLoading } = useAuth();
  return useQuery({
    queryKey: playlistKey(playlistId ?? "", user?.username ?? null),
    enabled: !isLoading && playlistId !== null,
    queryFn: async ({ signal }) => {
      const { data, error, response } = await api.GET("/api/playlists/{playlist_id}", {
        params: { path: { playlist_id: playlistId ?? "" } },
        signal,
      });
      if (data) return data;
      if (response.status === 404 || response.status === 422) throw new PlaylistNotFound();
      throw new Error(errorMessage(error));
    },
    retry: (failures, failure) => !(failure instanceof PlaylistNotFound) && failures < 1,
  });
}

export function useChannelPlaylists(username: string) {
  const { user, isLoading } = useAuth();
  return useInfiniteQuery({
    queryKey: [PLAYLISTS_KEY, "channel", username.toLowerCase(), user?.username ?? null],
    enabled: !isLoading,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) => {
      const { data, error } = await api.GET("/api/channels/{username}/playlists", {
        params: { path: { username }, query: { cursor: pageParam } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

/** The owner's changes to a playlist's items. Each answers with the playlist as it is now. */
export type ItemChange =
  { kind: "remove"; videoId: string } | { kind: "order"; videoIds: string[] };

export async function changeItems(
  client: Api,
  playlistId: string,
  change: ItemChange,
): Promise<Playlist> {
  const { data, error } =
    change.kind === "remove"
      ? await client.DELETE("/api/playlists/{playlist_id}/items/{video_id}", {
          params: { path: { playlist_id: playlistId, video_id: change.videoId } },
        })
      : await client.PUT("/api/playlists/{playlist_id}/items/order", {
          params: { path: { playlist_id: playlistId } },
          body: { video_ids: change.videoIds },
        });
  if (!data) throw new Error(errorMessage(error));
  return data;
}

/** `ids` with the one at `index` swapped with its neighbour `by` places away. */
export function moved(ids: string[], index: number, by: -1 | 1): string[] {
  const target = index + by;
  if (target < 0 || target >= ids.length) return ids;
  const next = [...ids];
  [next[index], next[target]] = [next[target]!, next[index]!];
  return next;
}

export function usePlaylistItems(playlistId: string) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (change: ItemChange) => changeItems(api, playlistId, change),
    onSuccess: (playlist) => {
      queryClient.setQueryData(playlistKey(playlistId, user?.username ?? null), playlist);
      void queryClient.invalidateQueries({
        queryKey: [PLAYLISTS_KEY],
        predicate: (query) => query.queryKey[1] !== "one",
      });
    },
  });
}

export function useDeletePlaylist(playlistId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await api.DELETE("/api/playlists/{playlist_id}", {
        params: { path: { playlist_id: playlistId } },
      });
      if (!response.ok) throw new Error(errorMessage(error));
    },
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: [PLAYLISTS_KEY, "one", playlistId] });
      void queryClient.invalidateQueries({ queryKey: [PLAYLISTS_KEY] });
    },
  });
}
