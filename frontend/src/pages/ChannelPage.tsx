import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Avatar } from "../components/Avatar";
import { LoadMore } from "../components/LoadMore";
import { PlaylistCard } from "../components/PlaylistCard";
import { ShortCard } from "../components/ShortCard";
import { SubscribeButton } from "../components/SubscribeButton";
import { VideoGridCard, VideoRowCard } from "../components/VideoCard";
import { GRID } from "../components/VideoFeed";
import { channelPath, formatSubscribers, videoCount } from "../components/format";
import { SearchIcon } from "../components/icons";
import { useAuth } from "../hooks/useAuth";
import {
  ChannelNotFound,
  VIDEO_SORTS,
  parseSort,
  useChannel,
  useChannelSearch,
  useChannelVideos,
  type Channel,
  type ChannelVideo,
  type VideoSort,
} from "../hooks/useChannel";
import { useChannelPlaylists } from "../hooks/usePlaylists";
import { useChannelShorts } from "../hooks/useShorts";
import { useRenewThumbnails } from "../hooks/useRenewThumbnails";
import { NotFoundPage } from "./NotFoundPage";

const BADGES: Record<ChannelVideo["visibility"], string | undefined> = {
  public: undefined,
  unlisted: "Unlisted",
  private: "Private",
};

const TABS = [
  { tab: "home", label: "Home" },
  { tab: "videos", label: "Videos" },
  { tab: "shorts", label: "Shorts" },
  { tab: "playlists", label: "Playlists" },
] as const;
type Tab = (typeof TABS)[number]["tab"] | "search";

/** How many cards a Home shelf shows before "View all", as on YouTube. */
const SHELF_SIZE = 12;

/** "@ana" from the path; anything else isn't a channel. */
export function handleToUsername(handle: string | undefined): string | null {
  if (!handle?.startsWith("@") || handle.length < 2) return null;
  return handle.slice(1);
}

const joined = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" });

const chip = (on: boolean) =>
  `rounded-lg px-3 py-1.5 text-sm font-medium ${
    on ? "bg-ink text-page" : "bg-hover hover:bg-hover-strong"
  }`;

const pill =
  "inline-flex h-9 items-center rounded-full bg-hover px-4 text-sm font-medium hover:bg-hover-strong";

function Banner({ channel }: { channel: Channel }) {
  const [failed, setFailed] = useState(false);
  if (!channel.banner_url || failed) return null;
  return (
    <img
      src={channel.banner_url}
      alt=""
      onError={() => setFailed(true)}
      className="mb-4 aspect-[6.2/1] w-full rounded-xl bg-hover object-cover"
    />
  );
}

/** YouTube's "About" box: the whole description and the channel's numbers. */
function AboutDialog({ channel, onClose }: { channel: Channel; onClose: () => void }) {
  const dialog = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  const link = `${window.location.origin}${channelPath(channel.username)}`;

  // The latest onClose, so a parent's re-render doesn't re-run the effect and steal focus.
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  }, [onClose]);

  useEffect(() => {
    // Back to whatever opened the box, when it closes.
    const opener = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close.current();
        return;
      }
      if (event.key !== "Tab" || !dialog.current) return;
      // Tab stays inside the box, as it's modal.
      const focusable = [
        ...dialog.current.querySelectorAll<HTMLElement>("button, a[href], [tabindex='0']"),
      ];
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first || !last) return;
      const outside = !dialog.current.contains(document.activeElement);
      if (event.shiftKey && (document.activeElement === first || outside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || outside)) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus();
    };
  }, []);

  useEffect(() => {
    if (!copied) return undefined;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  async function share() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      // No clipboard: the link is on screen to copy by hand.
    }
  }

  const facts: [string, string][] = [
    ["Link", link.replace(/^https?:\/\//, "")],
    ["Subscribers", formatSubscribers(channel.subscribers_count)],
    ["Videos", videoCount(channel.videos_count)],
    ["Views", `${channel.views_count.toLocaleString("en")} views`],
    ["Joined", `Joined ${joined.format(new Date(channel.created_at))}`],
  ];
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={onClose}>
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-title"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl bg-page p-6 shadow-xl outline-none"
      >
        <div className="flex items-start justify-between gap-4">
          <h2 id="about-title" className="text-xl font-bold">
            About
          </h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="grid size-9 place-items-center rounded-full text-xl hover:bg-hover"
          >
            ×
          </button>
        </div>
        {channel.description && (
          <p className="mt-3 text-sm wrap-anywhere whitespace-pre-wrap">{channel.description}</p>
        )}
        <h3 className="mt-6 text-lg font-bold">Channel details</h3>
        <dl className="mt-3 space-y-3 text-sm">
          {facts.map(([term, value]) => (
            <div key={term} className="flex gap-3">
              <dt className="sr-only">{term}</dt>
              <dd className="wrap-anywhere">{value}</dd>
            </div>
          ))}
        </dl>
        <button type="button" onClick={() => void share()} className={`mt-6 ${pill}`}>
          {copied ? "Link copied" : "Share channel"}
        </button>
      </div>
    </div>
  );
}

function Header({ channel }: { channel: Channel }) {
  const { user } = useAuth();
  const own = user?.username === channel.username;
  const [about, setAbout] = useState(false);
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
      <Avatar
        name={channel.display_name}
        username={channel.username}
        src={channel.avatar_url}
        className="size-20 text-4xl sm:size-40 sm:text-7xl"
      />
      <div className="min-w-0 space-y-2">
        <h1 className="text-2xl font-bold wrap-anywhere sm:text-4xl">{channel.display_name}</h1>
        <p className="text-sm text-ink-muted">
          <span className="font-medium text-ink">@{channel.username}</span> ·{" "}
          {formatSubscribers(channel.subscribers_count)} · {videoCount(channel.videos_count)}
        </p>
        <button
          type="button"
          onClick={() => setAbout(true)}
          className="flex max-w-xl gap-1 text-left text-sm text-ink-muted"
        >
          <span className="line-clamp-1 wrap-anywhere">
            {channel.description || "More about this channel"}
          </span>
          <span className="shrink-0 font-medium text-ink">...more</span>
        </button>
        <div className="flex flex-wrap gap-2 pt-1">
          {own ? (
            <>
              <Link to="/customize" className={pill}>
                Customize channel
              </Link>
              <Link to="/upload" className={pill}>
                Manage videos
              </Link>
            </>
          ) : (
            <SubscribeButton channel={channel} />
          )}
        </div>
      </div>
      {about && <AboutDialog channel={channel} onClose={() => setAbout(false)} />}
    </header>
  );
}

/** The magnifier at the end of the tabs, which opens into a search box for this channel. */
function ChannelSearch({ username, initial }: { username: string; initial: string }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(initial !== "");
  const [query, setQuery] = useState(initial);
  const input = useRef<HTMLInputElement>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (q.length < 2) return;
    void navigate(`${channelPath(username)}/search?query=${encodeURIComponent(q)}`);
  }

  if (!open) {
    return (
      <button
        type="button"
        aria-label="Search this channel"
        onClick={() => {
          setOpen(true);
          window.setTimeout(() => input.current?.focus());
        }}
        className="mb-1 ml-2 grid size-10 place-items-center rounded-full hover:bg-hover"
      >
        <SearchIcon />
      </button>
    );
  }
  return (
    <form role="search" onSubmit={submit} className="mb-1 ml-2 flex items-center gap-2">
      <SearchIcon />
      <input
        ref={input}
        type="search"
        aria-label="Search this channel"
        placeholder="Search"
        value={query}
        maxLength={100}
        onChange={(event) => setQuery(event.target.value)}
        className="w-32 border-b border-ink bg-transparent py-1 text-sm outline-none sm:w-48"
      />
    </form>
  );
}

function Failed({ what, retry }: { what: string; retry: () => unknown }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-4 p-16 text-center">
      <p className="text-ink-muted">Couldn't load {what}.</p>
      <button type="button" onClick={() => void retry()} className={pill}>
        Retry
      </button>
    </div>
  );
}

function SortChips({ current }: { current: VideoSort }) {
  const [params, setParams] = useSearchParams();
  return (
    <div role="group" aria-label="Sort by" className="mb-6 flex gap-3">
      {VIDEO_SORTS.map(({ sort, label }) => (
        <button
          key={sort}
          type="button"
          aria-pressed={sort === current}
          onClick={() => {
            const next = new URLSearchParams(params);
            if (sort === "latest") next.delete("sort");
            else next.set("sort", sort);
            setParams(next, { replace: true });
          }}
          className={chip(sort === current)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Videos({ username, sort }: { username: string; sort: VideoSort }) {
  const videos = useChannelVideos(username, sort);
  const renewThumbnails = useRenewThumbnails(videos);

  if (videos.isPending) return <div aria-busy="true" className="h-40" />;
  if (!videos.data) return <Failed what="videos" retry={videos.refetch} />;
  const items = videos.data.pages.flatMap((page) => page.items);
  if (items.length === 0) {
    return <p className="p-16 text-center text-ink-muted">This channel has no videos yet.</p>;
  }
  return (
    <>
      <SortChips current={sort} />
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

const SHORTS_GRID = "grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6";

function Shorts({ username, sort }: { username: string; sort: VideoSort }) {
  const shorts = useChannelShorts(username, sort);
  const renewThumbnails = useRenewThumbnails(shorts);

  if (shorts.isPending) return <div aria-busy="true" className="h-40" />;
  if (!shorts.data) return <Failed what="Shorts" retry={shorts.refetch} />;
  const items = shorts.data.pages.flatMap((page) => page.items);
  if (items.length === 0) {
    return <p className="p-16 text-center text-ink-muted">This channel has no Shorts.</p>;
  }
  return (
    <>
      <h2 className="sr-only">Shorts</h2>
      <SortChips current={sort} />
      <div className={SHORTS_GRID}>
        {items.map((video) => (
          <ShortCard
            key={video.id}
            video={video}
            badge={BADGES[video.visibility]}
            onThumbnailError={renewThumbnails}
          />
        ))}
      </div>
      <LoadMore pages={shorts} />
    </>
  );
}

function Playlists({ username }: { username: string }) {
  const playlists = useChannelPlaylists(username);
  const renewThumbnails = useRenewThumbnails(playlists);

  if (playlists.isPending) return <div aria-busy="true" className="h-40" />;
  if (!playlists.data) return <Failed what="playlists" retry={playlists.refetch} />;
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

function SearchResults({ username, query }: { username: string; query: string }) {
  const results = useChannelSearch(username, query);
  const renewThumbnails = useRenewThumbnails(results);

  if (query.trim().length < 2) {
    return <p className="p-16 text-center text-ink-muted">Search this channel's videos.</p>;
  }
  if (results.isPending) return <div aria-busy="true" className="h-40" />;
  if (!results.data) return <Failed what="results" retry={results.refetch} />;
  const items = results.data.pages.flatMap((page) => page.items);
  if (items.length === 0) {
    return (
      <p className="p-16 text-center text-ink-muted">
        This channel has no videos matching "{query.trim()}".
      </p>
    );
  }
  return (
    <>
      <h2 className="sr-only">Search results</h2>
      <div className="flex max-w-5xl flex-col gap-4">
        {items.map((video) => (
          <VideoRowCard key={video.id} video={video} onThumbnailError={renewThumbnails} />
        ))}
      </div>
      <LoadMore pages={results} />
    </>
  );
}

/** A row on the Home tab, scrolling sideways, with "View all" to the full tab. */
function Shelf({
  title,
  to,
  children,
}: {
  title: string;
  to: string;
  children: ReactNode;
}) {
  const id = `shelf-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <section aria-labelledby={id} className="border-b border-line py-6 last:border-b-0">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 id={id} className="text-xl font-bold">
          {title}
        </h2>
        <Link to={to} className="rounded-full px-3 py-1.5 text-sm font-medium hover:bg-hover">
          View all
        </Link>
      </div>
      {children}
    </section>
  );
}

// At most 4 videos (6 Shorts) across, as on YouTube, however few the shelf has.
const ROW =
  "grid auto-cols-[minmax(15rem,calc((100%-3rem)/4))] grid-flow-col gap-4 overflow-x-auto pb-1";
const SHORTS_ROW =
  "grid auto-cols-[minmax(9.5rem,calc((100%-5rem)/6))] grid-flow-col gap-4 overflow-x-auto pb-1";

/** YouTube's channel Home: the newest video up top, then shelves of the rest. */
function Home({ channel }: { channel: Channel }) {
  const username = channel.username;
  const latest = useChannelVideos(username, "latest");
  const popular = useChannelVideos(username, "popular");
  const shorts = useChannelShorts(username);
  const playlists = useChannelPlaylists(username);
  const renewLatest = useRenewThumbnails(latest);
  const renewPopular = useRenewThumbnails(popular);
  const renewShorts = useRenewThumbnails(shorts);
  const renewPlaylists = useRenewThumbnails(playlists);
  const { user } = useAuth();

  if (latest.isPending || shorts.isPending) return <div aria-busy="true" className="h-40" />;
  if (!latest.data) return <Failed what="videos" retry={latest.refetch} />;

  const videos = latest.data.pages[0]?.items ?? [];
  const shortItems = (shorts.data?.pages[0]?.items ?? []).slice(0, SHELF_SIZE);
  const popularItems = (popular.data?.pages[0]?.items ?? []).slice(0, SHELF_SIZE);
  const playlistItems = (playlists.data?.pages[0]?.items ?? []).slice(0, SHELF_SIZE);
  const base = channelPath(username);

  if (videos.length === 0 && shortItems.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 p-16 text-center">
        <p className="text-ink-muted">This channel has no videos yet.</p>
        {user?.username === username && (
          <Link to="/upload" className={pill}>
            Upload a video
          </Link>
        )}
      </div>
    );
  }
  const [featured, ...rest] = videos;
  return (
    <div>
      {featured && (
        <section aria-label="Featured video" className="border-b border-line pb-6">
          <VideoRowCard video={featured} onThumbnailError={renewLatest} />
        </section>
      )}
      {rest.length > 0 && (
        <Shelf title="Videos" to={`${base}/videos`}>
          <div className={ROW}>
            {rest.slice(0, SHELF_SIZE).map((video) => (
              <VideoGridCard
                key={video.id}
                video={video}
                showChannel={false}
                badge={BADGES[video.visibility]}
                onThumbnailError={renewLatest}
              />
            ))}
          </div>
        </Shelf>
      )}
      {shortItems.length > 0 && (
        <Shelf title="Shorts" to={`${base}/shorts`}>
          <div className={SHORTS_ROW}>
            {shortItems.map((video) => (
              <ShortCard
                key={video.id}
                video={video}
                badge={BADGES[video.visibility]}
                onThumbnailError={renewShorts}
              />
            ))}
          </div>
        </Shelf>
      )}
      {videos.length > 2 && popularItems.length > 0 && (
        <Shelf title="Popular videos" to={`${base}/videos?sort=popular`}>
          <div className={ROW}>
            {popularItems.map((video) => (
              <VideoGridCard
                key={video.id}
                video={video}
                showChannel={false}
                badge={BADGES[video.visibility]}
                onThumbnailError={renewPopular}
              />
            ))}
          </div>
        </Shelf>
      )}
      {playlistItems.length > 0 && (
        <Shelf title="Playlists" to={`${base}/playlists`}>
          <div className={ROW}>
            {playlistItems.map((playlist) => (
              <PlaylistCard
                key={playlist.id}
                playlist={playlist}
                onThumbnailError={renewPlaylists}
              />
            ))}
          </div>
        </Shelf>
      )}
    </div>
  );
}

function ChannelView({ username, current }: { username: string; current: Tab }) {
  const channel = useChannel(username);
  const [params] = useSearchParams();
  const sort = parseSort(params.get("sort"));
  const query = params.get("query") ?? "";

  if (channel.isError) {
    if (channel.error instanceof ChannelNotFound) return <NotFoundPage />;
    return (
      <p role="alert" className="p-6 text-center text-sm text-danger">
        Couldn't load this channel.
      </p>
    );
  }
  if (!channel.data) return <div aria-busy="true" className="h-40" />;

  const name = channel.data.username;
  return (
    <div className="mx-auto max-w-7xl px-4 pt-6 pb-10 sm:px-6">
      <Banner channel={channel.data} />
      <Header channel={channel.data} />
      <div className="mt-6 flex items-end overflow-x-auto border-b border-line">
        <nav aria-label="Channel" className="flex">
          {TABS.map(({ tab, label }) => (
            <Link
              key={tab}
              to={tab === "home" ? channelPath(name) : `${channelPath(name)}/${tab}`}
              aria-current={tab === current ? "page" : undefined}
              className={`border-b-2 px-3 pb-3 font-medium whitespace-nowrap ${
                tab === current ? "border-ink" : "border-transparent text-ink-muted hover:border-line"
              }`}
            >
              {label}
            </Link>
          ))}
        </nav>
        <ChannelSearch key={query} username={name} initial={current === "search" ? query : ""} />
      </div>
      <div className="mt-6">
        {current === "home" && <Home channel={channel.data} />}
        {current === "videos" && <Videos username={name} sort={sort} />}
        {current === "shorts" && <Shorts username={name} sort={sort} />}
        {current === "playlists" && <Playlists username={name} />}
        {current === "search" && <SearchResults username={name} query={query} />}
      </div>
    </div>
  );
}

export function ChannelPage() {
  const { handle, tab = "home" } = useParams();
  const username = handleToUsername(handle);
  const current: Tab | undefined =
    tab === "search" ? "search" : TABS.find((entry) => entry.tab === tab)?.tab;
  if (!username || !current) return <NotFoundPage />;
  // Another channel starts from a clean page.
  return <ChannelView key={username.toLowerCase()} username={username} current={current} />;
}
