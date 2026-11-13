import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Comments } from "../components/Comments";
import { nextInPlaylist, PlaylistPanel } from "../components/PlaylistPanel";
import { ReactionButtons } from "../components/ReactionButtons";
import { SubscribeButton } from "../components/SubscribeButton";
import { channelPath, formatSubscribers, watchPath } from "../components/format";
import { useChannel } from "../hooks/useChannel";
import { usePlaylist } from "../hooks/usePlaylists";
import { VideoPlayer } from "../components/VideoPlayer";
import { statusMessage, useVideo, VideoNotFound, type VideoDetails } from "../hooks/useVideo";
import { NotFoundPage } from "./NotFoundPage";

/** Avatar, name and subscriber count link to the channel; Subscribe sits beside them. */
function ChannelRow({ video }: { video: VideoDetails }) {
  const channel = useChannel(video.channel.username);
  const href = channelPath(video.channel.username);
  return (
    <div className="flex min-w-0 items-center gap-3">
      <Link
        to={href}
        tabIndex={-1}
        aria-hidden
        className="grid size-10 shrink-0 place-items-center rounded-full bg-accent font-medium text-white"
      >
        {video.channel.display_name.charAt(0).toUpperCase()}
      </Link>
      <div className="min-w-0">
        <p className="truncate font-medium">
          <Link to={href}>{video.channel.display_name}</Link>
        </p>
        <p className="truncate text-xs text-ink-muted">
          {channel.data
            ? formatSubscribers(channel.data.subscribers_count)
            : `@${video.channel.username}`}
        </p>
      </div>
      {channel.data && (
        <div className="ml-2">
          <SubscribeButton channel={channel.data} />
        </div>
      )}
    </div>
  );
}

function Details({ video }: { video: VideoDetails }) {
  const published = video.published_at ?? video.created_at;
  return (
    <>
      <h1 className="mt-3 text-xl font-semibold wrap-anywhere">{video.title}</h1>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <ChannelRow video={video} />
        {video.status === "ready" && <ReactionButtons video={video} />}
      </div>
      <div className="mt-3 rounded-xl bg-hover p-3 text-sm">
        <p className="font-medium">
          {video.views_count.toLocaleString()} views · {new Date(published).toLocaleDateString()}
        </p>
        {video.description && <p className="mt-2 wrap-anywhere whitespace-pre-wrap">{video.description}</p>}
      </div>
    </>
  );
}

function Watch({ videoId, playlistId }: { videoId: string; playlistId: string | null }) {
  const video = useVideo(videoId);
  const navigate = useNavigate();
  // A playlist the caller can't see, or a broken link, just plays the video alone.
  const playlist = usePlaylist(playlistId).data ?? null;
  const next = playlist ? nextInPlaylist(playlist, videoId) : null;
  const playNext = next && playlist ? () => void navigate(watchPath(next, playlist.id)) : undefined;

  if (video.isError) {
    if (video.error instanceof VideoNotFound) return <NotFoundPage />;
    return (
      <p role="alert" className="p-6 text-center text-sm text-red-700">
        Couldn't load this video.
      </p>
    );
  }

  const message = video.data ? statusMessage(video.data.status) : null;
  const main = (
    <div className="min-w-0 flex-1">
      {video.isPending && <div className="aspect-video w-full rounded-xl bg-hover" />}
      {message !== null && (
        <div className="grid aspect-video w-full place-items-center rounded-xl bg-black p-6 text-center text-white">
          {message}
        </div>
      )}
      {video.data?.status === "ready" && (
        <VideoPlayer
          videoId={videoId}
          poster={video.data.thumbnail_url ?? undefined}
          onEnded={playNext}
        />
      )}
      {video.data && <Details video={video.data} />}
      {video.data?.status === "ready" && <Comments video={video.data} />}
    </div>
  );
  if (!playlist) return <div className="mx-auto max-w-5xl px-4 py-6">{main}</div>;
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 lg:flex-row lg:items-start">
      {main}
      <PlaylistPanel playlist={playlist} videoId={videoId} />
    </div>
  );
}

export function WatchPage() {
  const [params] = useSearchParams();
  const videoId = params.get("v");
  const playlistId = params.get("list");
  if (!videoId) return <NotFoundPage />;
  // A new video starts from a clean page, not with the last one's details on screen.
  return <Watch key={videoId} videoId={videoId} playlistId={playlistId} />;
}
