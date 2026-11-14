import { Link } from "react-router-dom";

import type { OwnerVideo } from "../api/upload";
import { useDeleteVideo, useMyVideos } from "../hooks/useMyVideos";

const VISIBILITY: Record<OwnerVideo["visibility"], string> = {
  public: "Public",
  unlisted: "Unlisted",
  private: "Private",
};

function StatusBadge({ status }: { status: OwnerVideo["status"] }) {
  const base = "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium";
  switch (status) {
    case "uploading":
      return <span className={`${base} bg-hover text-ink-muted`}>Upload not finished</span>;
    case "processing":
      return (
        <span className={`${base} bg-accent-soft text-accent`}>
          <span
            aria-hidden
            className="size-3 animate-spin rounded-full border-2 border-accent/30 border-t-accent"
          />
          Processing
        </span>
      );
    case "ready":
      return <span className={`${base} bg-green-100 text-green-800`}>Ready</span>;
    case "failed":
      return <span className={`${base} bg-danger-soft text-danger`}>Failed</span>;
  }
}

export function MyVideos() {
  const videos = useMyVideos();
  const remove = useDeleteVideo();

  function confirmDelete(video: OwnerVideo) {
    if (window.confirm(`Delete "${video.title}"? This can't be undone.`)) remove.mutate(video.id);
  }

  if (videos.isPending) return null;
  if (videos.isError) {
    return (
      <p role="alert" className="text-sm text-danger">
        Couldn't load your videos.
      </p>
    );
  }

  const items = videos.data.pages.flatMap((page) => page.items);
  if (items.length === 0) return <p className="text-sm text-ink-muted">No videos yet.</p>;

  return (
    <>
      {remove.isError && (
        <p role="alert" className="mb-2 text-sm text-danger">
          {remove.error.message}
        </p>
      )}
      <ul className="divide-y divide-line">
        {items.map((video) => (
          <li key={video.id} className="flex items-center justify-between gap-4 py-3">
            <div className="min-w-0">
              {video.status === "ready" ? (
                <Link
                  to={`/watch?v=${video.id}`}
                  className="block truncate font-medium hover:text-accent"
                >
                  {video.title}
                </Link>
              ) : (
                <p className="truncate font-medium">{video.title}</p>
              )}
              <p className="text-sm text-ink-muted">
                {VISIBILITY[video.visibility]} · {new Date(video.created_at).toLocaleDateString()}
              </p>
              {video.status === "failed" && video.failure_reason && (
                <p className="text-sm text-danger">{video.failure_reason}</p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <StatusBadge status={video.status} />
              <button
                type="button"
                aria-label={`Delete ${video.title}`}
                disabled={remove.isPending}
                onClick={() => confirmDelete(video)}
                className="h-8 rounded-full px-3 text-sm hover:bg-hover disabled:opacity-50"
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
      {videos.hasNextPage && (
        <button
          type="button"
          disabled={videos.isFetchingNextPage}
          onClick={() => void videos.fetchNextPage()}
          className="mt-3 h-9 rounded-full px-4 text-sm font-medium text-accent hover:bg-accent-soft disabled:opacity-50"
        >
          Load more
        </button>
      )}
    </>
  );
}
