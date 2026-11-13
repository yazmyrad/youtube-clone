import { LoadMore } from "../components/LoadMore";
import { VideoGridCard } from "../components/VideoCard";
import { useFeed } from "../hooks/useFeed";

const GRID = "grid gap-x-4 gap-y-10 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4";

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

export function HomePage() {
  const feed = useFeed();

  let body;
  if (feed.isPending) {
    body = (
      <div className={GRID} aria-busy="true">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} />
        ))}
      </div>
    );
  } else if (feed.isError) {
    body = (
      <div role="alert" className="flex flex-col items-center gap-4 p-16 text-center">
        <p className="text-ink-muted">Couldn't load videos.</p>
        <button
          type="button"
          onClick={() => feed.refetch()}
          className="rounded-full bg-hover px-4 py-2 text-sm font-medium hover:bg-hover-strong"
        >
          Retry
        </button>
      </div>
    );
  } else {
    const videos = feed.data.pages.flatMap((page) => page.items);
    body =
      videos.length === 0 ? (
        <p className="p-16 text-center text-ink-muted">
          No videos yet. Be the first to upload one.
        </p>
      ) : (
        <>
          <div className={GRID}>
            {videos.map((video) => (
              <VideoGridCard key={video.id} video={video} />
            ))}
          </div>
          <LoadMore
            hasMore={feed.hasNextPage}
            loading={feed.isFetchingNextPage}
            onMore={() => feed.fetchNextPage()}
          />
        </>
      );
  }

  return <div className="px-4 pt-6 pb-10 sm:px-6">{body}</div>;
}
