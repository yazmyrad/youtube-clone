import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { channelPath, formatDuration, videoCount, watchPath } from "../components/format";
import { PlayIcon } from "../components/icons";
import { useAuth } from "../hooks/useAuth";
import {
  moved,
  PlaylistNotFound,
  useDeletePlaylist,
  usePlaylist,
  usePlaylistItems,
  type Playlist,
} from "../hooks/usePlaylists";
import { useRenewThumbnails } from "../hooks/useRenewThumbnails";
import { NotFoundPage } from "./NotFoundPage";

const VISIBILITY = { public: "Public", unlisted: "Unlisted", private: "Private" } as const;

const SMALL_BUTTON =
  "grid size-8 place-items-center rounded-full text-sm hover:bg-hover disabled:opacity-40";

function Header({ playlist, own }: { playlist: Playlist; own: boolean }) {
  const navigate = useNavigate();
  const remove = useDeletePlaylist(playlist.id);
  const first = playlist.items[0];

  async function deletePlaylist() {
    if (!window.confirm(`Delete "${playlist.title}"? Its videos stay.`)) return;
    await remove.mutateAsync();
    void navigate(`${channelPath(playlist.channel.username)}/playlists`);
  }

  return (
    <header className="rounded-2xl bg-hover p-6 lg:sticky lg:top-20 lg:w-90 lg:shrink-0">
      <div className="aspect-video overflow-hidden rounded-xl bg-hover-strong">
        {playlist.thumbnail_url && (
          <img src={playlist.thumbnail_url} alt="" className="size-full object-cover" />
        )}
      </div>
      <h1 className="mt-4 text-2xl font-bold wrap-anywhere">{playlist.title}</h1>
      <p className="mt-2 text-sm font-medium">
        <Link to={channelPath(playlist.channel.username)} className="hover:underline">
          {playlist.channel.display_name}
        </Link>
      </p>
      <p className="mt-1 text-xs text-ink-muted">
        {VISIBILITY[playlist.visibility]} · {videoCount(playlist.video_count)} · Updated{" "}
        {new Date(playlist.updated_at).toLocaleDateString()}
      </p>
      {playlist.description && (
        <p className="mt-3 text-sm wrap-anywhere whitespace-pre-wrap">{playlist.description}</p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {first && (
          <Link
            to={watchPath(first.id, playlist.id)}
            className="flex h-9 items-center gap-2 rounded-full bg-ink px-4 text-sm font-medium text-page hover:opacity-85"
          >
            <PlayIcon />
            Play all
          </Link>
        )}
        {own && (
          <button
            type="button"
            onClick={() => void deletePlaylist()}
            disabled={remove.isPending}
            className="h-9 rounded-full bg-page px-4 text-sm font-medium hover:bg-hover-strong"
          >
            Delete playlist
          </button>
        )}
      </div>
      {remove.isError && (
        <p role="alert" className="mt-2 text-xs text-red-700">
          {remove.error.message}
        </p>
      )}
    </header>
  );
}

function Items({ playlist, own }: { playlist: Playlist; own: boolean }) {
  const items = usePlaylistItems(playlist.id);
  const query = usePlaylist(playlist.id);
  const renewThumbnails = useRenewThumbnails(query);
  const ids = playlist.items.map((video) => video.id);

  if (playlist.items.length === 0) {
    return <p className="p-16 text-center text-ink-muted">No videos in this playlist yet.</p>;
  }
  return (
    <div className="min-w-0 flex-1">
      {items.isError && (
        <p role="alert" className="mb-2 text-sm text-red-700">
          {items.error.message}
        </p>
      )}
      <ol>
        {playlist.items.map((video, index) => (
          <li key={video.id} className="flex items-center gap-3 rounded-xl p-2 hover:bg-hover">
            <span className="w-6 shrink-0 text-center text-sm text-ink-muted">{index + 1}</span>
            <Link
              to={watchPath(video.id, playlist.id)}
              tabIndex={-1}
              aria-hidden
              className="relative aspect-video w-40 shrink-0 overflow-hidden rounded-lg bg-hover"
            >
              <img
                src={video.thumbnail_url}
                alt=""
                loading="lazy"
                onError={renewThumbnails}
                className="size-full object-cover"
              />
              <span className="absolute right-1 bottom-1 rounded bg-black/80 px-1 text-xs font-medium text-white">
                {formatDuration(video.duration_seconds)}
              </span>
            </Link>
            <div className="min-w-0 flex-1">
              <h2 className="line-clamp-2 font-medium">
                <Link to={watchPath(video.id, playlist.id)} title={video.title}>
                  {video.title}
                </Link>
              </h2>
              <p className="truncate text-sm text-ink-muted">
                <Link to={channelPath(video.channel.username)} className="hover:text-ink">
                  {video.channel.display_name}
                </Link>
              </p>
            </div>
            {own && (
              <div className="flex shrink-0 items-center">
                <button
                  type="button"
                  aria-label={`Move "${video.title}" up`}
                  disabled={index === 0 || items.isPending}
                  onClick={() => items.mutate({ kind: "order", videoIds: moved(ids, index, -1) })}
                  className={SMALL_BUTTON}
                >
                  ↑
                </button>
                <button
                  type="button"
                  aria-label={`Move "${video.title}" down`}
                  disabled={index === ids.length - 1 || items.isPending}
                  onClick={() => items.mutate({ kind: "order", videoIds: moved(ids, index, 1) })}
                  className={SMALL_BUTTON}
                >
                  ↓
                </button>
                <button
                  type="button"
                  aria-label={`Remove "${video.title}" from the playlist`}
                  disabled={items.isPending}
                  onClick={() => items.mutate({ kind: "remove", videoId: video.id })}
                  className={SMALL_BUTTON}
                >
                  ✕
                </button>
              </div>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function PlaylistView({ playlistId }: { playlistId: string }) {
  const { user } = useAuth();
  const playlist = usePlaylist(playlistId);

  if (playlist.isError) {
    if (playlist.error instanceof PlaylistNotFound) return <NotFoundPage />;
    return (
      <p role="alert" className="p-6 text-center text-sm text-red-700">
        Couldn't load this playlist.
      </p>
    );
  }
  if (!playlist.data) return <div aria-busy="true" className="h-40" />;

  const own = user?.username === playlist.data.channel.username;
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 pt-6 pb-10 sm:px-6 lg:flex-row lg:items-start">
      <Header playlist={playlist.data} own={own} />
      <Items playlist={playlist.data} own={own} />
    </div>
  );
}

export function PlaylistPage() {
  const [params] = useSearchParams();
  const playlistId = params.get("list");
  if (!playlistId) return <NotFoundPage />;
  return <PlaylistView key={playlistId} playlistId={playlistId} />;
}
