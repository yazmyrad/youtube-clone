import { Link } from "react-router-dom";

import type { PlaylistSummary } from "../hooks/usePlaylists";
import { playlistPath, videoCount } from "./format";
import { PlaylistIcon } from "./icons";

const VISIBILITY = { public: null, unlisted: "Unlisted", private: "Private" } as const;

/** YouTube's playlist tile: the first video's picture with the count over it. */
export function PlaylistCard({
  playlist,
  onThumbnailError,
}: {
  playlist: PlaylistSummary;
  onThumbnailError?: () => void;
}) {
  const href = playlistPath(playlist.id);
  const label = VISIBILITY[playlist.visibility];
  return (
    <article>
      <Link to={href} tabIndex={-1} aria-hidden className="block">
        <div className="relative aspect-video overflow-hidden rounded-xl bg-hover">
          {playlist.thumbnail_url && (
            <img
              src={playlist.thumbnail_url}
              alt=""
              loading="lazy"
              onError={onThumbnailError}
              className="size-full object-cover"
            />
          )}
          <span className="absolute right-1.5 bottom-1.5 flex items-center gap-1 rounded bg-black/80 px-1 text-xs font-medium text-white">
            <PlaylistIcon />
            {videoCount(playlist.video_count)}
          </span>
        </div>
      </Link>
      <h3 className="mt-3 line-clamp-2 leading-snug font-medium">
        <Link to={href} title={playlist.title}>
          {playlist.title}
        </Link>
      </h3>
      {label && (
        <p className="mt-1 inline-block rounded bg-hover px-1.5 text-xs font-medium text-ink-muted">
          {label}
        </p>
      )}
      <p className="mt-1 text-sm">
        <Link to={href} className="text-ink-muted hover:text-ink">
          View full playlist
        </Link>
      </p>
    </article>
  );
}
