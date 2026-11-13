import type { ReactNode } from "react";

import { useRenewThumbnails, type Renewable } from "../hooks/useRenewThumbnails";
import { LoadMore, type Pages } from "./LoadMore";
import { VideoGridCard, type VideoCardData } from "./VideoCard";

export const GRID = "grid gap-x-4 gap-y-10 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4";

/** The parts of an infinite query of video cards that a feed shows. */
interface FeedQuery extends Pages, Renewable {
  isPending: boolean;
  data: { pages: { items: VideoCardData[] }[] } | undefined;
}

function Skeleton() {
  return (
    <div aria-hidden>
      <div className="aspect-video rounded-xl bg-hover" />
      <div className="mt-3 flex gap-3">
        <div className="size-9 shrink-0 rounded-full bg-hover" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-11/12 rounded bg-hover" />
          <div className="h-4 w-2/3 rounded bg-hover" />
        </div>
      </div>
    </div>
  );
}

/** A grid of video cards with YouTube's endless scrolling, and its loading, error and empty
 * states. `heading` is shown above the grid once there are videos. */
export function VideoFeed({
  query,
  heading,
  empty,
}: {
  query: FeedQuery;
  heading: ReactNode;
  empty: ReactNode;
}) {
  const renewThumbnails = useRenewThumbnails(query);

  if (query.isPending) {
    return (
      <div className={GRID} aria-busy="true">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} />
        ))}
      </div>
    );
  }
  if (!query.data) {
    return (
      <div role="alert" className="flex flex-col items-center gap-4 p-16 text-center">
        <p className="text-ink-muted">Couldn't load videos.</p>
        <button
          type="button"
          onClick={() => query.refetch()}
          className="rounded-full bg-hover px-4 py-2 text-sm font-medium hover:bg-hover-strong"
        >
          Retry
        </button>
      </div>
    );
  }
  const videos = query.data.pages.flatMap((page) => page.items);
  if (videos.length === 0) return <>{empty}</>;
  return (
    <>
      {heading}
      <div className={GRID}>
        {videos.map((video) => (
          <VideoGridCard key={video.id} video={video} onThumbnailError={renewThumbnails} />
        ))}
      </div>
      <LoadMore pages={query} />
    </>
  );
}
