import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Avatar } from "../components/Avatar";
import { Comments } from "../components/Comments";
import { HiddenNotice } from "../components/HiddenNotice";
import { HideButton } from "../components/HideButton";
import { nextInPlaylist, PlaylistPanel } from "../components/PlaylistPanel";
import { ReactionButtons } from "../components/ReactionButtons";
import { ReportButton } from "../components/ReportButton";
import { SaveButton } from "../components/SaveButton";
import { SubscribeButton } from "../components/SubscribeButton";
import { UpNext } from "../components/UpNext";
import { channelPath, formatAge, formatSubscribers, watchPath } from "../components/format";
import { useChannel } from "../hooks/useChannel";
import { useFeedFirstPage } from "../hooks/useFeed";
import { usePlaylist } from "../hooks/usePlaylists";
import { useRenewThumbnails } from "../hooks/useRenewThumbnails";
import { VideoPlayer } from "../components/VideoPlayer";
import { statusMessage, useVideo, VideoNotFound, type VideoDetails } from "../hooks/useVideo";
import { NotFoundPage } from "./NotFoundPage";

/** Avatar, name and subscriber count link to the channel; Subscribe sits beside them. */
function ChannelRow({ video }: { video: VideoDetails }) {
  const channel = useChannel(video.channel.username);
  const href = channelPath(video.channel.username);
  return (
    <div className="flex min-w-0 items-center gap-3">
      <Link to={href} tabIndex={-1} aria-hidden>
        <Avatar
          name={video.channel.display_name}
          username={video.channel.username}
          src={video.channel.avatar_url}
          className="size-10"
        />
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

/** Ready and not hidden: what can be played, liked, saved, reported and commented on. */
function playable(video: VideoDetails): boolean {
  return video.status === "ready" && !video.hidden_at;
}

function Details({ video }: { video: VideoDetails }) {
  const published = video.published_at ?? video.created_at;
  return (
    <>
      <h1 className="mt-3 text-xl font-semibold wrap-anywhere">{video.title}</h1>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <ChannelRow video={video} />
        {playable(video) && (
          <div className="flex flex-wrap items-start gap-2">
            <ReactionButtons video={video} />
            <SaveButton videoId={video.id} />
            <ReportButton videoId={video.id} owner={video.channel.username} />
            <HideButton videoId={video.id} />
          </div>
        )}
      </div>
      <div className="mt-3 rounded-xl bg-hover p-3 text-sm">
        <p className="font-medium">
          {video.views_count.toLocaleString("en")} {video.views_count === 1 ? "view" : "views"}
          <time dateTime={published} title={new Date(published).toLocaleString()} className="ml-2">
            {formatAge(published)}
          </time>
        </p>
        {video.description && (
          <p className="mt-2 wrap-anywhere whitespace-pre-wrap">{video.description}</p>
        )}
      </div>
    </>
  );
}

const THEATER_KEY = "player.theater";

/** Theater mode, remembered across videos and visits as YouTube does. */
function useTheater(): [boolean, () => void] {
  const [theater, setTheater] = useState(() => {
    try {
      return localStorage.getItem(THEATER_KEY) === "1";
    } catch {
      return false;
    }
  });
  const toggle = () =>
    setTheater((value) => {
      try {
        localStorage.setItem(THEATER_KEY, value ? "0" : "1");
      } catch {
        // Not remembered, then.
      }
      return !value;
    });
  return [theater, toggle];
}

function Watch({
  videoId,
  playlistId,
  theater,
  onTheater,
}: {
  videoId: string;
  playlistId: string | null;
  theater: boolean;
  onTheater: () => void;
}) {
  const video = useVideo(videoId);
  const navigate = useNavigate();
  // A playlist the caller can't see, or a broken link, just plays the video alone.
  const playlistQuery = usePlaylist(playlistId);
  const playlist = playlistQuery.data ?? null;
  const renewPlaylist = useRenewThumbnails(playlistQuery);
  const next = playlist ? nextInPlaylist(playlist, videoId) : null;
  const playNext = next && playlist ? () => void navigate(watchPath(next, playlist.id)) : undefined;
  // Next: the playlist's next video, or else the first one Up next lists.
  const upNext = useFeedFirstPage().data?.find((item) => item.id !== videoId);
  const goNext = playNext ?? (upNext ? () => void navigate(watchPath(upNext.id)) : undefined);

  if (video.isError) {
    if (video.error instanceof VideoNotFound) return <NotFoundPage />;
    return (
      <p role="alert" className="p-6 text-center text-sm text-danger">
        Couldn't load this video.
      </p>
    );
  }

  const message = video.data ? statusMessage(video.data.status) : null;
  const player = video.data && playable(video.data) && (
    <VideoPlayer
      videoId={videoId}
      poster={video.data.thumbnail_url ?? undefined}
      onEnded={playNext}
      onNext={goNext}
      theater={theater}
      onTheater={onTheater}
    />
  );
  // One tree for both layouts, so switching to theater mode never remounts the player, which
  // would restart the video. Only the grid placement changes: as on YouTube, the player and
  // details on the left and the playlist and Up next on the right; in theater mode the player
  // spans the window on a black band, with the rest below. On narrow screens, one column.
  return (
    <div className="overflow-x-clip">
      <div className="mx-auto grid max-w-[1754px] grid-cols-1 px-4 pt-6 pb-10 lg:grid-cols-[minmax(0,1fr)_400px] lg:grid-rows-[auto_auto_1fr] lg:gap-x-6 lg:px-6">
        <div
          data-testid="player-slot"
          className={
            theater
              ? "-mt-6 ml-[calc(50%-50vw)] w-screen bg-black lg:col-span-2"
              : "min-w-0 lg:col-start-1 lg:row-start-1"
          }
        >
          {video.isPending && <div className="aspect-video w-full rounded-xl bg-hover" />}
          {video.data?.hidden_at && <HiddenNotice video={video.data} />}
          {message !== null && !video.data?.hidden_at && (
            <div className="grid aspect-video w-full place-items-center rounded-xl bg-black p-6 text-center text-white">
              {message}
            </div>
          )}
          {player}
        </div>
        <div className="min-w-0 lg:col-start-1 lg:row-start-2">
          {video.data && <Details video={video.data} />}
          {video.data && playable(video.data) && <Comments video={video.data} />}
        </div>
        <aside
          className={`mt-6 space-y-4 lg:col-start-2 ${
            theater ? "lg:row-span-2 lg:row-start-2" : "lg:row-span-3 lg:row-start-1 lg:mt-0"
          }`}
        >
          {playlist && (
            <PlaylistPanel playlist={playlist} videoId={videoId} onThumbnailError={renewPlaylist} />
          )}
          <UpNext videoId={videoId} />
        </aside>
      </div>
    </div>
  );
}

export function WatchPage() {
  const [params] = useSearchParams();
  const videoId = params.get("v");
  const playlistId = params.get("list");
  const [theater, toggleTheater] = useTheater();
  if (!videoId) return <NotFoundPage />;
  // A new video starts from a clean page, not with the last one's details on screen.
  return (
    <Watch
      key={videoId}
      videoId={videoId}
      playlistId={playlistId}
      theater={theater}
      onTheater={toggleTheater}
    />
  );
}
