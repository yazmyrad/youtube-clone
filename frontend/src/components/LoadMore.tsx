import { useEffect, useRef } from "react";

/** The parts of an infinite query that LoadMore uses. */
export interface Pages {
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  isFetchNextPageError: boolean;
  fetchNextPage: () => unknown;
}

/** Loads the next page when the end of a list scrolls into view, like YouTube's endless feed.
 * The button is the fallback without IntersectionObserver and for keyboard users. After a
 * failed page it waits for a click, so a failing API is not retried in a loop. */
export function LoadMore({ pages }: { pages: Pages }) {
  const { hasNextPage, isFetchingNextPage: loading, isFetchNextPageError: failed } = pages;
  const ref = useRef<HTMLDivElement>(null);
  const pagesRef = useRef(pages);

  useEffect(() => {
    pagesRef.current = pages;
  });

  useEffect(() => {
    const node = ref.current;
    if (!node || !hasNextPage || loading || failed) return undefined;
    if (typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) pagesRef.current.fetchNextPage();
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasNextPage, loading, failed]);

  if (!hasNextPage) return null;
  return (
    <div ref={ref} className="flex flex-col items-center gap-2 py-6">
      {loading ? (
        <span
          role="status"
          aria-label="Loading"
          className="size-8 animate-spin rounded-full border-4 border-hover border-t-ink-muted"
        />
      ) : (
        <>
          {failed && (
            <p role="alert" className="text-sm text-ink-muted">
              Couldn't load more videos.
            </p>
          )}
          <button
            type="button"
            onClick={() => pages.fetchNextPage()}
            className="rounded-full bg-hover px-4 py-2 text-sm font-medium hover:bg-hover-strong"
          >
            {failed ? "Retry" : "Show more"}
          </button>
        </>
      )}
    </div>
  );
}
