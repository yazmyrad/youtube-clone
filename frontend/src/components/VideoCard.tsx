import { Link } from "react-router-dom";

import type { components } from "../api/schema";
import { formatAge, formatDuration, formatViews } from "./format";

export type VideoCardData = components["schemas"]["VideoCardOut"];

function Thumbnail({ video }: { video: VideoCardData }) {
  return (
    <div className="relative aspect-video overflow-hidden rounded-xl bg-hover">
      <img src={video.thumbnail_url} alt="" loading="lazy" className="size-full object-cover" />
      <span className="absolute right-1.5 bottom-1.5 rounded bg-black/80 px-1 text-xs font-medium text-white">
        {formatDuration(video.duration_seconds)}
      </span>
    </div>
  );
}

function Avatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden
      className="grid size-9 shrink-0 place-items-center rounded-full bg-accent text-sm font-medium text-white uppercase"
    >
      {name.slice(0, 1)}
    </span>
  );
}

function Meta({ video }: { video: VideoCardData }) {
  return (
    <p className="text-sm text-ink-muted">
      {formatViews(video.views_count)} · {formatAge(video.published_at)}
    </p>
  );
}

/** A card in the home grid: thumbnail on top, then avatar, title and channel. */
export function VideoGridCard({ video }: { video: VideoCardData }) {
  const href = `/watch?v=${video.id}`;
  return (
    <article>
      <Link to={href} tabIndex={-1} aria-hidden>
        <Thumbnail video={video} />
      </Link>
      <div className="mt-3 flex gap-3">
        <Avatar name={video.channel.display_name} />
        <div className="min-w-0">
          <h3 className="line-clamp-2 leading-snug font-medium">
            <Link to={href} title={video.title}>
              {video.title}
            </Link>
          </h3>
          <p className="mt-1 truncate text-sm text-ink-muted">{video.channel.display_name}</p>
          <Meta video={video} />
        </div>
      </div>
    </article>
  );
}

/** A row in search results: thumbnail on the left, details on the right. */
export function VideoRowCard({ video }: { video: VideoCardData }) {
  const href = `/watch?v=${video.id}`;
  return (
    <article className="flex flex-col gap-3 sm:flex-row sm:gap-4">
      <Link to={href} tabIndex={-1} aria-hidden className="shrink-0 sm:w-90">
        <Thumbnail video={video} />
      </Link>
      <div className="min-w-0">
        <h3 className="line-clamp-2 text-lg leading-snug">
          <Link to={href} title={video.title}>
            {video.title}
          </Link>
        </h3>
        <Meta video={video} />
        <p className="mt-3 flex items-center gap-2 text-sm text-ink-muted">
          <Avatar name={video.channel.display_name} />
          <span className="truncate">{video.channel.display_name}</span>
        </p>
      </div>
    </article>
  );
}
