import { useEffect, useRef } from "react";

/** Loads the next page when the end of a list scrolls into view, like YouTube's endless feed.
 * The button is the fallback without IntersectionObserver and for keyboard users. */
export function LoadMore({
  hasMore,
  loading,
  onMore,
}: {
  hasMore: boolean;
  loading: boolean;
  onMore: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const onMoreRef = useRef(onMore);
  onMoreRef.current = onMore;

  useEffect(() => {
    const node = ref.current;
    if (!node || !hasMore || loading || typeof IntersectionObserver === "undefined")
      return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) onMoreRef.current();
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loading]);

  if (!hasMore) return null;
  return (
    <div ref={ref} className="flex justify-center py-6">
      {loading ? (
        <span
          role="status"
          aria-label="Loading"
          className="size-8 animate-spin rounded-full border-4 border-hover border-t-ink-muted"
        />
      ) : (
        <button
          type="button"
          onClick={onMore}
          className="rounded-full bg-hover px-4 py-2 text-sm font-medium hover:bg-hover-strong"
        >
          Show more
        </button>
      )}
    </div>
  );
}
