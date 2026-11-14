import { Link } from "react-router-dom";

import type { ShortCardData } from "../hooks/useShorts";
import { formatViews, shortPath } from "./format";

/** A Short on a shelf or a tab: a tall thumbnail, the title and the views, as on YouTube. */
export function ShortCard({
  video,
  onThumbnailError,
  badge,
}: {
  video: ShortCardData;
  onThumbnailError?: () => void;
  /** A note such as "Private", on the owner's own tab. */
  badge?: string;
}) {
  const href = shortPath(video.id);
  return (
    <article className="min-w-0">
      <Link to={href} tabIndex={-1} aria-hidden className="block">
        <div className="aspect-[9/16] overflow-hidden rounded-xl bg-hover">
          <img
            src={video.thumbnail_url}
            alt=""
            loading="lazy"
            onError={onThumbnailError}
            className="size-full object-cover"
          />
        </div>
      </Link>
      <h3 className="mt-2 line-clamp-2 text-sm leading-snug font-medium">
        <Link to={href} title={video.title}>
          {video.title}
        </Link>
      </h3>
      <p className="mt-0.5 text-sm text-ink-muted">{formatViews(video.views_count)}</p>
      {badge && (
        <p className="mt-1 inline-block rounded bg-hover px-1.5 text-xs font-medium text-ink-muted">
          {badge}
        </p>
      )}
    </article>
  );
}
