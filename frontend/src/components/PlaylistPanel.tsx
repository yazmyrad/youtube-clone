import { Link } from "react-router-dom";

import type { Playlist } from "../hooks/usePlaylists";
import { formatDuration, playlistPath, watchPath } from "./format";

/** The video after `videoId` in the playlist, or null at the end or if it isn't there. */
export function nextInPlaylist(playlist: Playlist, videoId: string): string | null {
  const index = playlist.items.findIndex((video) => video.id === videoId);
  if (index < 0) return null;
  return playlist.items[index + 1]?.id ?? null;
}

/** The list beside the player while watching a playlist, as on YouTube. */
export function PlaylistPanel({
  playlist,
  videoId,
  onThumbnailError,
}: {
  playlist: Playlist;
  videoId: string;
  /** Called when an image fails, usually because its signed URL expired. */
  onThumbnailError?: () => void;
}) {
  const index = playlist.items.findIndex((video) => video.id === videoId);
  return (
    <section
      aria-label="Playlist"
      className="overflow-hidden rounded-xl border border-line"
    >
      <header className="bg-hover px-4 py-3">
        <h2 className="truncate text-lg font-bold">
          <Link to={playlistPath(playlist.id)}>{playlist.title}</Link>
        </h2>
        <p className="text-xs text-ink-muted">
          {playlist.channel.display_name} ·{" "}
          {index >= 0
            ? `${index + 1} / ${playlist.items.length}`
            : `${playlist.items.length} videos`}
        </p>
      </header>
      <ol className="max-h-[28rem] overflow-y-auto py-2">
        {playlist.items.map((video, position) => {
          const current = video.id === videoId;
          return (
            <li key={video.id}>
              <Link
                to={watchPath(video.id, playlist.id)}
                aria-current={current ? "true" : undefined}
                className={`flex items-center gap-2 px-2 py-1 hover:bg-hover ${current ? "bg-hover-strong" : ""}`}
              >
                <span className="w-5 shrink-0 text-center text-xs text-ink-muted">
                  {current ? "▶" : position + 1}
                </span>
                <span className="relative aspect-video w-24 shrink-0 overflow-hidden rounded-md bg-hover">
                  <img
                    src={video.thumbnail_url}
                    alt=""
                    loading="lazy"
                    onError={onThumbnailError}
                    className="size-full object-cover"
                  />
                  <span className="absolute right-0.5 bottom-0.5 rounded bg-black/80 px-0.5 text-[10px] font-medium text-white">
                    {formatDuration(video.duration_seconds)}
                  </span>
                </span>
                <span className="min-w-0">
                  <span className="line-clamp-2 text-sm font-medium">{video.title}</span>
                  <span className="block truncate text-xs text-ink-muted">
                    {video.channel.display_name}
                  </span>
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
