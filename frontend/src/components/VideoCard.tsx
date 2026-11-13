import { Link } from "react-router-dom";

import type { components } from "../api/schema";
import { channelPath, formatAge, formatDuration, formatViews } from "./format";

export type VideoCardData = components["schemas"]["VideoCardOut"];

interface CardProps {
  video: VideoCardData;
  /** Called when the image fails, usually because its signed URL expired. */
  onThumbnailError?: () => void;
}

interface GridCardProps extends CardProps {
  /** Off on the channel's own page, where every card is from that channel. */
  showChannel?: boolean;
  /** A note under the meta line, such as "Private". */
  badge?: string;
}

function Thumbnail({ video, onThumbnailError }: CardProps) {
  return (
    <div className="relative aspect-video overflow-hidden rounded-xl bg-hover">
      <img
        src={video.thumbnail_url}
        alt=""
        loading="lazy"
        onError={onThumbnailError}
        className="size-full object-cover"
      />
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
      {Array.from(name)[0] ?? "?"}
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

function ChannelLink({ video }: { video: VideoCardData }) {
  return (
    <Link to={channelPath(video.channel.username)} className="hover:text-ink">
      {video.channel.display_name}
    </Link>
  );
}

/** A card in the home grid: thumbnail on top, then avatar, title and channel. */
export function VideoGridCard({
  video,
  onThumbnailError,
  showChannel = true,
  badge,
}: GridCardProps) {
  const href = `/watch?v=${video.id}`;
  return (
    <article>
      <Link to={href} tabIndex={-1} aria-hidden>
        <Thumbnail video={video} onThumbnailError={onThumbnailError} />
      </Link>
      <div className="mt-3 flex gap-3">
        {showChannel && (
          <Link to={channelPath(video.channel.username)} tabIndex={-1} aria-hidden>
            <Avatar name={video.channel.display_name} />
          </Link>
        )}
        <div className="min-w-0">
          <h2 className="line-clamp-2 leading-snug font-medium">
            <Link to={href} title={video.title}>
              {video.title}
            </Link>
          </h2>
          {showChannel && (
            <p className="mt-1 truncate text-sm text-ink-muted">
              <ChannelLink video={video} />
            </p>
          )}
          <Meta video={video} />
          {badge && (
            <p className="mt-1 inline-block rounded bg-hover px-1.5 text-xs font-medium text-ink-muted">
              {badge}
            </p>
          )}
        </div>
      </div>
    </article>
  );
}

/** A row in search results: thumbnail on the left, details on the right. */
export function VideoRowCard({ video, onThumbnailError }: CardProps) {
  const href = `/watch?v=${video.id}`;
  return (
    <article className="flex flex-col gap-3 sm:flex-row sm:gap-4">
      <Link to={href} tabIndex={-1} aria-hidden className="shrink-0 sm:w-90">
        <Thumbnail video={video} onThumbnailError={onThumbnailError} />
      </Link>
      <div className="min-w-0">
        <h2 className="line-clamp-2 text-lg leading-snug">
          <Link to={href} title={video.title}>
            {video.title}
          </Link>
        </h2>
        <Meta video={video} />
        <p className="mt-3 flex items-center gap-2 text-sm text-ink-muted">
          <Link to={channelPath(video.channel.username)} tabIndex={-1} aria-hidden>
            <Avatar name={video.channel.display_name} />
          </Link>
          <span className="truncate">
            <ChannelLink video={video} />
          </span>
        </p>
      </div>
    </article>
  );
}
