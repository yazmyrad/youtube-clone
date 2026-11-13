import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Api } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";
import { useAuth } from "./useAuth";
import { SUBSCRIPTIONS_KEY } from "./useSubscriptions";

export type Channel = components["schemas"]["ChannelOut"];
export type ChannelVideo = components["schemas"]["ChannelVideoOut"];
type SubscriptionState = components["schemas"]["SubscriptionStateOut"];

/** 404: no user by that name. */
export class ChannelNotFound extends Error {}

/** The account is part of the key, as `is_subscribed` and the owner's videos depend on it. */
export function channelKey(username: string, viewer: string | null) {
  return ["channel", username.toLowerCase(), viewer];
}

export function useChannel(username: string) {
  const { user, isLoading } = useAuth();
  return useQuery({
    queryKey: channelKey(username, user?.username ?? null),
    enabled: !isLoading,
    queryFn: async ({ signal }) => {
      const { data, error, response } = await api.GET("/api/channels/{username}", {
        params: { path: { username } },
        signal,
      });
      if (data) return data;
      if (response.status === 404) throw new ChannelNotFound();
      throw new Error(errorMessage(error));
    },
    retry: (failures, failure) => !(failure instanceof ChannelNotFound) && failures < 1,
  });
}

export function useChannelVideos(username: string) {
  const { user, isLoading } = useAuth();
  return useInfiniteQuery({
    queryKey: [...channelKey(username, user?.username ?? null), "videos"],
    enabled: !isLoading,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) => {
      const { data, error } = await api.GET("/api/channels/{username}/videos", {
        params: { path: { username }, query: { cursor: pageParam } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

export async function sendSubscription(
  client: Api,
  username: string,
  subscribe: boolean,
): Promise<SubscriptionState> {
  const params = { path: { username } };
  const { data, error } = subscribe
    ? await client.PUT("/api/channels/{username}/subscription", { params })
    : await client.DELETE("/api/channels/{username}/subscription", { params });
  if (!data) throw new Error(errorMessage(error));
  return data;
}

export function useSubscription(username: string) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (subscribe: boolean) => sendSubscription(api, username, subscribe),
    onSuccess: (state) => {
      queryClient.setQueryData<Channel>(
        channelKey(username, user?.username ?? null),
        (channel) => channel && { ...channel, ...state },
      );
      // The sidebar list and the subscriptions feed now differ.
      void queryClient.invalidateQueries({ queryKey: [SUBSCRIPTIONS_KEY] });
    },
  });
}
