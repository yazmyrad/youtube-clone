import { useFeedFirstPage } from "../hooks/useFeed";
import { useRenewThumbnails } from "../hooks/useRenewThumbnails";
import { VideoCompactCard } from "./VideoCard";

/** How many the column lists: one page of the feed. */
export const UP_NEXT = 12;

/** The column beside the player: the latest public videos but the one playing. There are no
 * recommendations, so the newest is the best guess at what to watch next. */
export function UpNext({ videoId }: { videoId: string }) {
  const feed = useFeedFirstPage();
  const renewThumbnails = useRenewThumbnails(feed);
  const videos = (feed.data ?? []).filter((video) => video.id !== videoId).slice(0, UP_NEXT);

  if (feed.isPending) {
    return (
      <div aria-busy="true" className="space-y-2">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="flex gap-2">
            <div className="aspect-video w-42 shrink-0 rounded-xl bg-hover" />
            <div className="flex-1 space-y-2">
              <div className="h-3 rounded bg-hover" />
              <div className="h-3 w-2/3 rounded bg-hover" />
            </div>
          </div>
        ))}
      </div>
    );
  }
  // A side list: nothing to say when it can't load or is empty.
  if (videos.length === 0) return null;
  return (
    <section aria-label="Up next" className="space-y-2">
      {videos.map((video) => (
        <VideoCompactCard key={video.id} video={video} onThumbnailError={renewThumbnails} />
      ))}
    </section>
  );
}
