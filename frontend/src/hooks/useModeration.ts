import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Api } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";
import { useAuth } from "./useAuth";

export type ReportReason = components["schemas"]["ReportReason"];
export type QueueEntry = components["schemas"]["QueueEntryOut"];

/** In the order the report dialog offers them, with YouTube-like wording. */
export const REPORT_REASONS: { value: ReportReason; label: string }[] = [
  { value: "spam", label: "Spam or misleading" },
  { value: "violence", label: "Violent or repulsive content" },
  { value: "sexual", label: "Sexual content" },
  { value: "copyright", label: "Infringes my rights" },
  { value: "other", label: "Something else" },
];

export function isModerator(role: string | undefined): boolean {
  return role === "moderator" || role === "admin";
}

export async function sendReport(
  client: Api,
  videoId: string,
  reason: ReportReason,
  details: string,
): Promise<void> {
  const { data, error } = await client.POST("/api/videos/{video_id}/reports", {
    params: { path: { video_id: videoId } },
    body: { reason, details },
  });
  if (!data) throw new Error(errorMessage(error));
}

export function useReport(videoId: string) {
  return useMutation({
    mutationFn: ({ reason, details }: { reason: ReportReason; details: string }) =>
      sendReport(api, videoId, reason, details),
  });
}

/** A moderator's decision. Each answers once the server has applied it. */
export type Decision =
  | { kind: "hide"; videoId: string; reason: string }
  | { kind: "restore"; videoId: string }
  | { kind: "resolve" | "dismiss"; reportId: string };

export async function decide(client: Api, decision: Decision): Promise<void> {
  let result: { error?: unknown; response: Response };
  switch (decision.kind) {
    case "hide":
      result = await client.POST("/api/moderation/videos/{video_id}/hide", {
        params: { path: { video_id: decision.videoId } },
        body: { reason: decision.reason },
      });
      break;
    case "restore":
      result = await client.POST("/api/moderation/videos/{video_id}/restore", {
        params: { path: { video_id: decision.videoId } },
        body: { reason: "" },
      });
      break;
    case "resolve":
      result = await client.POST("/api/moderation/reports/{report_id}/resolve", {
        params: { path: { report_id: decision.reportId } },
        body: { reason: "" },
      });
      break;
    case "dismiss":
      result = await client.POST("/api/moderation/reports/{report_id}/dismiss", {
        params: { path: { report_id: decision.reportId } },
        body: { reason: "" },
      });
      break;
  }
  if (!result.response.ok) throw new Error(errorMessage(result.error));
}

/** After a decision every view of the video may be stale: its details, the feeds, the
 * queue. Reloading them all is simplest, and decisions are rare. */
export function useDecide() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (decision: Decision) => decide(api, decision),
    onSettled: () => queryClient.invalidateQueries(),
  });
}

export function useReportQueue() {
  const { user } = useAuth();
  return useInfiniteQuery({
    queryKey: ["moderation", "queue", user?.username ?? null],
    enabled: isModerator(user?.role),
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) => {
      const { data, error } = await api.GET("/api/moderation/reports", {
        params: { query: { cursor: pageParam } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}
