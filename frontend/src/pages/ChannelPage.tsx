import { Link, NavLink, useParams } from "react-router-dom";

import { Avatar } from "../components/Avatar";
import { LoadMore } from "../components/LoadMore";
import { PlaylistCard } from "../components/PlaylistCard";
import { SubscribeButton } from "../components/SubscribeButton";
import { VideoGridCard } from "../components/VideoCard";
import { GRID } from "../components/VideoFeed";
import { channelPath, formatSubscribers } from "../components/format";
import { useAuth } from "../hooks/useAuth";
import {
  ChannelNotFound,
  useChannel,
  useChannelVideos,
  type Channel,
  type ChannelVideo,
} from "../hooks/useChannel";
import { useChannelPlaylists } from "../hooks/usePlaylists";
import { useRenewThumbnails } from "../hooks/useRenewThumbnails";
import { NotFoundPage } from "./NotFoundPage";

const BADGES: Record<ChannelVideo["visibility"], string | undefined> = {
  public: undefined,
  unlisted: "Unlisted",
  private: "Private",
};

const TABS = [
  { tab: "videos", label: "Videos" },
  { tab: "playlists", label: "Playlists" },
] as const;
type Tab = (typeof TABS)[number]["tab"];

/** "@ana" from the path; anything else isn't a channel. */
export function handleToUsername(handle: string | undefined): string | null {
  if (!handle?.startsWith("@") || handle.length < 2) return null;
  return handle.slice(1);
}

function Header({ channel }: { channel: Channel }) {
  const { user } = useAuth();
  const own = user?.username === channel.username;
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
      <Avatar
        name={channel.display_name}
        username={channel.username}
        className="size-20 text-4xl sm:size-40 sm:text-7xl"
      />
      <div className="min-w-0 space-y-2">
        <h1 className="text-2xl font-bold wrap-anywhere sm:text-4xl">{channel.display_name}</h1>
        <p className="text-sm text-ink-muted">
          <span className="font-medium text-ink">@{channel.username}</span> ·{" "}
          {formatSubscribers(channel.subscribers_count)}
        </p>
        {channel.description && (
          <p className="line-clamp-2 text-sm wrap-anywhere whitespace-pre-wrap text-ink-muted">
            {channel.description}
          </p>
        )}
        <div className="pt-1">
          {own ? (
            <Link
              to="/upload"
              className="inline-flex h-9 items-center rounded-full bg-hover px-4 text-sm font-medium hover:bg-hover-strong"
            >
              Manage videos
            </Link>
          ) : (
            <SubscribeButton channel={channel} />
          )}
        </div>
      </div>
    </header>
  );
}

function Videos({ username }: { username: string }) {
  const videos = useChannelVideos(username);
  const renewThumbnails = useRenewThumbnails(videos);

  if (videos.isPending) return <div aria-busy="true" className="h-40" />;
  if (!videos.data) {
    return (
      <div role="alert" className="flex flex-col items-center gap-4 p-16 text-center">
        <p className="text-ink-muted">Couldn't load videos.</p>
        <button
          type="button"
          onClick={() => videos.refetch()}
          className="rounded-full bg-hover px-4 py-2 text-sm font-medium hover:bg-hover-strong"
        >
          Retry
        </button>
      </div>
    );
  }
  const items = videos.data.pages.flatMap((page) => page.items);
  if (items.length === 0) {
    return <p className="p-16 text-center text-ink-muted">This channel has no videos yet.</p>;
  }
  return (
    <>
      <div className={GRID}>
        {items.map((video) => (
          <VideoGridCard
            key={video.id}
            video={video}
            showChannel={false}
            badge={BADGES[video.visibility]}
            onThumbnailError={renewThumbnails}
          />
        ))}
      </div>
      <LoadMore pages={videos} />
    </>
  );
}

function Playlists({ username }: { username: string }) {
  const playlists = useChannelPlaylists(username);
  const renewThumbnails = useRenewThumbnails(playlists);

  if (playlists.isPending) return <div aria-busy="true" className="h-40" />;
  if (!playlists.data) {
    return (
      <div role="alert" className="flex flex-col items-center gap-4 p-16 text-center">
        <p className="text-ink-muted">Couldn't load playlists.</p>
        <button
          type="button"
          onClick={() => playlists.refetch()}
          className="rounded-full bg-hover px-4 py-2 text-sm font-medium hover:bg-hover-strong"
        >
          Retry
        </button>
      </div>
    );
  }
  const items = playlists.data.pages.flatMap((page) => page.items);
  if (items.length === 0) {
    return <p className="p-16 text-center text-ink-muted">This channel has no playlists.</p>;
  }
  return (
    <>
      <h2 className="sr-only">Playlists</h2>
      <div className={GRID}>
        {items.map((playlist) => (
          <PlaylistCard key={playlist.id} playlist={playlist} onThumbnailError={renewThumbnails} />
        ))}
      </div>
      <LoadMore pages={playlists} />
    </>
  );
}

function ChannelView({ username, current }: { username: string; current: Tab }) {
  const channel = useChannel(username);

  if (channel.isError) {
    if (channel.error instanceof ChannelNotFound) return <NotFoundPage />;
    return (
      <p role="alert" className="p-6 text-center text-sm text-danger">
        Couldn't load this channel.
      </p>
    );
  }
  if (!channel.data) return <div aria-busy="true" className="h-40" />;

  return (
    <div className="mx-auto max-w-7xl px-4 pt-6 pb-10 sm:px-6">
      <Header channel={channel.data} />
      <nav aria-label="Channel" className="mt-6 flex border-b border-line">
        {TABS.map(({ tab, label }) => (
          <NavLink
            key={tab}
            to={`${channelPath(channel.data.username)}/${tab}`}
            aria-current={tab === current ? "page" : undefined}
            className={`border-b-2 px-3 pb-3 font-medium ${
              tab === current ? "border-ink" : "border-transparent text-ink-muted hover:border-line"
            }`}
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-6">
        {current === "videos" ? (
          <Videos username={channel.data.username} />
        ) : (
          <Playlists username={channel.data.username} />
        )}
      </div>
    </div>
  );
}

export function ChannelPage() {
  const { handle, tab = "videos" } = useParams();
  const username = handleToUsername(handle);
  const current = TABS.find((entry) => entry.tab === tab)?.tab;
  if (!username || !current) return <NotFoundPage />;
  // Another channel starts from a clean page.
  return <ChannelView key={username.toLowerCase()} username={username} current={current} />;
}
