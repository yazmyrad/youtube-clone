import { useCallback } from "react";

/** Thumbnail URLs are signed for one to two hours. */
export const MIN_RENEW_AGE_MS = 60_000;

/** The parts of a query that renewing thumbnails uses. */
export interface Renewable {
  dataUpdatedAt: number;
  isFetching: boolean;
  refetch: () => unknown;
}

/** Whether a broken thumbnail should reload the list. A list fetched within the last minute
 * has fresh URLs, so a broken image there is not an expiry and a reload would loop. */
export function shouldRenew(query: Renewable, now: number = Date.now()): boolean {
  return !query.isFetching && now - query.dataUpdatedAt >= MIN_RENEW_AGE_MS;
}

/** Returns a handler for a thumbnail that failed to load: it fetches the list again, which
 * signs new URLs. */
export function useRenewThumbnails(query: Renewable) {
  const { dataUpdatedAt, isFetching, refetch } = query;
  return useCallback(() => {
    if (shouldRenew({ dataUpdatedAt, isFetching, refetch })) refetch();
  }, [dataUpdatedAt, isFetching, refetch]);
}
