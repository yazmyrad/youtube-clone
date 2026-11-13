import { Link, useLocation } from "react-router-dom";

import { LoadMore } from "../components/LoadMore";
import { VideoRowCard } from "../components/VideoCard";
import { HistoryIcon } from "../components/icons";
import { useAuth } from "../hooks/useAuth";
import { useForget, useHistory } from "../hooks/useHistory";
import { useRenewThumbnails } from "../hooks/useRenewThumbnails";

function SignedOut() {
  const { pathname } = useLocation();
  return (
    <div className="flex flex-col items-center gap-4 p-16 text-center">
      <span className="text-ink-muted [&_svg]:size-24">
        <HistoryIcon />
      </span>
      <h1 className="text-2xl">Keep track of what you watch</h1>
      <p className="text-sm text-ink-muted">Watch history isn't viewable when signed out.</p>
      <Link
        to={`/login?next=${encodeURIComponent(pathname)}`}
        className="rounded-full border border-line px-4 py-2 text-sm font-medium text-accent hover:bg-accent-soft"
      >
        Sign in
      </Link>
    </div>
  );
}

function History() {
  const history = useHistory();
  const forget = useForget();
  const renewThumbnails = useRenewThumbnails(history);

  function clearAll() {
    if (window.confirm("Clear all watch history?")) forget.mutate(null);
  }

  let body;
  if (history.isPending) {
    body = <div aria-busy="true" className="h-40" />;
  } else if (!history.data) {
    body = (
      <div role="alert" className="flex flex-col items-center gap-4 p-16 text-center">
        <p className="text-ink-muted">Couldn't load your history.</p>
        <button
          type="button"
          onClick={() => history.refetch()}
          className="rounded-full bg-hover px-4 py-2 text-sm font-medium hover:bg-hover-strong"
        >
          Retry
        </button>
      </div>
    );
  } else {
    const entries = history.data.pages.flatMap((page) => page.items);
    body =
      entries.length === 0 ? (
        <p className="py-16 text-ink-muted">Videos you watch will show up here.</p>
      ) : (
        <>
          <ol className="space-y-4">
            {entries.map(({ video, progress_seconds }) => (
              <li key={video.id} className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <VideoRowCard
                    video={video}
                    progress={progress_seconds / Math.max(1, video.duration_seconds)}
                    onThumbnailError={renewThumbnails}
                  />
                </div>
                <button
                  type="button"
                  aria-label={`Remove "${video.title}" from watch history`}
                  disabled={forget.isPending}
                  onClick={() => forget.mutate(video.id)}
                  className="grid size-10 shrink-0 place-items-center rounded-full hover:bg-hover"
                >
                  ✕
                </button>
              </li>
            ))}
          </ol>
          <LoadMore pages={history} />
        </>
      );
  }

  return (
    <div className="flex flex-col-reverse gap-6 lg:flex-row lg:items-start">
      <div className="min-w-0 flex-1">
        <h1 className="mb-6 text-3xl font-bold">Watch history</h1>
        {body}
      </div>
      <aside className="lg:w-60 lg:pt-16">
        <button
          type="button"
          onClick={clearAll}
          disabled={forget.isPending}
          className="flex h-9 items-center rounded-full px-4 text-sm font-medium hover:bg-hover"
        >
          Clear all watch history
        </button>
        {forget.isError && (
          <p role="alert" className="mt-2 text-xs text-red-700">
            {forget.error.message}
          </p>
        )}
      </aside>
    </div>
  );
}

export function HistoryPage() {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;
  return (
    <div className="mx-auto max-w-6xl px-4 pt-6 pb-10 sm:px-6">
      {user ? <History /> : <SignedOut />}
    </div>
  );
}
