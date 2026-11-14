import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { errorMessage } from "../api/errors";
import { Avatar } from "../components/Avatar";
import { Comments } from "../components/Comments";
import { SubscribeButton } from "../components/SubscribeButton";
import { channelPath, shortPath } from "../components/format";
import { ThumbDownIcon, ThumbUpIcon } from "../components/icons";
import { PauseGlyph, PlayGlyph, VolumeHighGlyph, VolumeOffGlyph } from "../components/player/icons";
import { isForPlayer } from "../components/player/shortcuts";
import { usePlayback, FAILURE_TEXT } from "../components/player/usePlayback";
import { useMediaState } from "../components/player/useMediaState";
import { useAuth } from "../hooks/useAuth";
import { useChannel } from "../hooks/useChannel";
import { nextReaction, useReaction, type Reaction } from "../hooks/useReaction";
import { useShortsFeed, type ShortCardData } from "../hooks/useShorts";
import { useVideo, type VideoDetails } from "../hooks/useVideo";
import { useViewHeartbeat } from "../hooks/useViewHeartbeat";

/** Remembered across Shorts, as YouTube does: once unmuted, the next one plays with sound. */
const MUTED_KEY = "shorts.muted";

function readMuted(): boolean {
  try {
    return localStorage.getItem(MUTED_KEY) === "1";
  } catch {
    return false;
  }
}

function saveMuted(muted: boolean) {
  try {
    localStorage.setItem(MUTED_KEY, muted ? "1" : "0");
  } catch {
    // Not remembered, then.
  }
}

/** The video, looping, with YouTube's tap-to-pause, a mute button and a thin progress line. */
function ShortPlayer({ videoId, poster }: { videoId: string; poster: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const { failure } = usePlayback(videoRef, videoId);
  const media = useMediaState(videoRef);
  const [muted, setMuted] = useState(readMuted);
  const [flash, setFlash] = useState<"play" | "pause" | null>(null);
  useViewHeartbeat(videoRef, videoId);

  useEffect(() => {
    const video = videoRef.current;
    if (video) video.muted = muted;
  }, [muted]);

  // Browsers refuse to start a video with sound before the page was touched: start it muted.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return undefined;
    const onCanPlay = () => {
      void video.play()?.catch(() => {
        video.muted = true;
        setMuted(true);
        void video.play()?.catch(() => {});
      });
    };
    video.addEventListener("canplay", onCanPlay, { once: true });
    return () => video.removeEventListener("canplay", onCanPlay);
  }, []);

  const toggle = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      void video.play()?.catch(() => {});
      setFlash("play");
    } else {
      video.pause();
      setFlash("pause");
    }
  }, []);

  const toggleMute = useCallback(() => {
    setMuted((value) => {
      saveMuted(!value);
      return !value;
    });
  }, []);

  useEffect(() => {
    if (!flash) return undefined;
    const timer = window.setTimeout(() => setFlash(null), 600);
    return () => window.clearTimeout(timer);
  }, [flash]);

  // Only the Short on screen has a player, so these keys always mean that one.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat || !isForPlayer(event.target, event.key)) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key === " " || event.key === "k" || event.key === "K") {
        event.preventDefault();
        toggle();
      } else if (event.key === "m" || event.key === "M") {
        event.preventDefault();
        toggleMute();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [toggle, toggleMute]);

  const progress = media.duration > 0 ? (media.currentTime / media.duration) * 100 : 0;
  return (
    <>
      <video ref={videoRef} poster={poster} loop playsInline className="size-full object-cover" />
      {failure ? (
        <p
          role="alert"
          className="absolute inset-0 grid place-items-center p-6 text-center text-white"
        >
          {FAILURE_TEXT[failure]}
        </p>
      ) : (
        <>
          <button
            type="button"
            aria-label={media.paused ? "Play" : "Pause"}
            onClick={toggle}
            className="absolute inset-0 cursor-pointer"
          />
          {flash && (
            <span
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-1/2 grid size-16 -translate-x-1/2 -translate-y-1/2 animate-player-flash place-items-center rounded-full bg-black/60 p-4 text-white motion-reduce:animate-none"
            >
              {flash === "play" ? <PlayGlyph /> : <PauseGlyph />}
            </span>
          )}
          {media.paused && !flash && (
            <span
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-1/2 grid size-16 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-black/60 p-4 text-white"
            >
              <PlayGlyph />
            </span>
          )}
          <button
            type="button"
            aria-label={muted ? "Unmute (m)" : "Mute (m)"}
            aria-pressed={muted}
            onClick={toggleMute}
            className="absolute top-3 right-3 grid size-10 place-items-center rounded-full bg-black/40 p-2 text-white hover:bg-black/60"
          >
            {muted ? <VolumeOffGlyph /> : <VolumeHighGlyph />}
          </button>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-1 bg-white/30">
            <div className="h-full bg-[#f00]" style={{ width: `${progress}%` }} />
          </div>
        </>
      )}
    </>
  );
}

function ActionButton({
  label,
  count,
  pressed,
  disabled,
  onClick,
  children,
}: {
  label: string;
  count?: string;
  pressed?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      <button
        type="button"
        aria-label={label}
        aria-pressed={pressed}
        disabled={disabled}
        onClick={onClick}
        className={`grid size-12 place-items-center rounded-full bg-hover hover:bg-hover-strong disabled:opacity-60 ${
          pressed ? "text-accent" : ""
        }`}
      >
        {children}
      </button>
      {count !== undefined && <span className="text-xs font-medium">{count}</span>}
    </div>
  );
}

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

/** Like, dislike, comments and share, beside the Short as on YouTube. */
function ShortActions({
  video,
  commentsOpen,
  onComments,
}: {
  video: VideoDetails;
  commentsOpen: boolean;
  onComments: () => void;
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const react = useReaction(video.id);
  const [copied, setCopied] = useState(false);

  function press(pressed: Reaction) {
    if (!user) {
      void navigate(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    react.mutate(nextReaction(video.my_reaction, pressed));
  }

  async function share() {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${shortPath(video.id)}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // No clipboard (an old browser, or not allowed): nothing to copy to.
    }
  }

  return (
    <div className="relative flex flex-col items-center gap-4">
      <ActionButton
        label="Like"
        count={compact.format(video.likes_count)}
        pressed={video.my_reaction === "like"}
        disabled={react.isPending}
        onClick={() => press("like")}
      >
        <ThumbUpIcon />
      </ActionButton>
      <ActionButton
        label="Dislike"
        count="Dislike"
        pressed={video.my_reaction === "dislike"}
        disabled={react.isPending}
        onClick={() => press("dislike")}
      >
        <ThumbDownIcon />
      </ActionButton>
      <ActionButton
        label="Comments"
        count={compact.format(video.comments_count)}
        pressed={commentsOpen}
        onClick={onComments}
      >
        <svg viewBox="0 0 24 24" className="size-6" fill="currentColor" aria-hidden>
          <path d="M20 2H4a2 2 0 0 0-2 2v18l4-4h14a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2zm0 14H5.17L4 17.17V4h16v12z" />
        </svg>
      </ActionButton>
      <ActionButton label="Share" count="Share" onClick={() => void share()}>
        <svg viewBox="0 0 24 24" className="size-6" fill="currentColor" aria-hidden>
          <path d="M14 9V5l7 7-7 7v-4.1c-5 0-8.5 1.6-11 5.1 1-5 4-10 11-11z" />
        </svg>
      </ActionButton>
      {copied && (
        <span
          role="status"
          className="absolute -top-10 right-0 rounded-lg bg-ink px-3 py-1.5 text-xs whitespace-nowrap text-page"
        >
          Link copied
        </span>
      )}
    </div>
  );
}

/** The channel and title over the bottom of the Short. */
function ShortInfo({ video }: { video: ShortCardData }) {
  const channel = useChannel(video.channel.username);
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-4 pt-16 pb-5 text-white">
      <div className="pointer-events-auto flex items-center gap-2">
        <Link to={channelPath(video.channel.username)} className="flex min-w-0 items-center gap-2">
          <Avatar
            name={video.channel.display_name}
            username={video.channel.username}
            className="size-8 text-sm"
          />
          <span className="truncate text-sm font-medium">@{video.channel.username}</span>
        </Link>
        {channel.data && <SubscribeButton channel={channel.data} />}
      </div>
      <h2 className="mt-2 line-clamp-2 text-sm font-medium">{video.title}</h2>
    </div>
  );
}

function ShortItem({
  video,
  active,
  commentsOpen,
  onComments,
}: {
  video: ShortCardData;
  active: boolean;
  commentsOpen: boolean;
  onComments: () => void;
}) {
  // Details (likes, comments) only for the Short on screen.
  const details = useVideo(video.id, active);
  return (
    <div className="flex h-full items-end justify-center gap-4">
      <div className="relative aspect-[9/16] h-full max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl bg-black">
        {active ? (
          <ShortPlayer videoId={video.id} poster={video.thumbnail_url} />
        ) : (
          <img src={video.thumbnail_url} alt="" className="size-full object-cover" />
        )}
        <ShortInfo video={video} />
      </div>
      <div className="hidden w-12 shrink-0 sm:block">
        {active && details.data && (
          <ShortActions video={details.data} commentsOpen={commentsOpen} onComments={onComments} />
        )}
      </div>
      {active && commentsOpen && details.data && (
        <aside
          aria-label="Comments"
          className="absolute inset-x-0 bottom-0 z-10 h-[70%] overflow-y-auto rounded-t-2xl border border-line bg-page px-4 pb-4 shadow-xl lg:static lg:h-full lg:w-100 lg:rounded-xl lg:shadow-none"
        >
          <button
            type="button"
            onClick={onComments}
            className="sticky top-0 float-right mt-2 rounded-full px-3 py-1 text-sm hover:bg-hover"
          >
            Close
          </button>
          <Comments video={details.data} />
        </aside>
      )}
    </div>
  );
}

/** The Shorts to scroll through: the one asked for first, then the feed. */
function useShortQueue(id: string | undefined) {
  const feed = useShortsFeed();
  const items = feed.data?.pages.flatMap((page) => page.items) ?? [];
  const inFeed = id !== undefined && items.some((item) => item.id === id);
  // A Short that isn't in the loaded feed (shared link, older, unlisted): fetch it alone.
  const single = useQuery({
    queryKey: ["video", id ?? "", "as-short"],
    enabled: id !== undefined && feed.isFetched && !inFeed,
    queryFn: async ({ signal }) => {
      const { data, error } = await api.GET("/api/videos/{video_id}", {
        params: { path: { video_id: id ?? "" } },
        signal,
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
  });
  let queue = items;
  if (id !== undefined && !inFeed && single.data) {
    const extra: ShortCardData = {
      id: single.data.id,
      title: single.data.title,
      duration_seconds: single.data.duration_seconds ?? 0,
      views_count: single.data.views_count,
      published_at: single.data.published_at ?? single.data.created_at,
      thumbnail_url: single.data.thumbnail_url ?? "",
      channel: single.data.channel,
      is_short: single.data.is_short,
    };
    queue = [extra, ...items];
  }
  return { feed, queue, single, inFeed };
}

export function ShortsPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { feed, queue, single, inFeed } = useShortQueue(id);
  const scroller = useRef<HTMLDivElement>(null);
  const [activeId, setActiveId] = useState<string | undefined>(id);
  const [commentsOpen, setCommentsOpen] = useState(false);

  // /shorts alone opens the first Short; a regular video asked for as a Short opens normally.
  useEffect(() => {
    if (id === undefined && queue[0]) void navigate(shortPath(queue[0].id), { replace: true });
  }, [id, queue, navigate]);
  useEffect(() => {
    if (id && single.data && !single.data.is_short) {
      void navigate(`/watch?v=${encodeURIComponent(id)}`, { replace: true });
    }
  }, [id, single.data, navigate]);

  // Opened from a shelf: start at that Short.
  const scrolledTo = useRef(false);
  useEffect(() => {
    if (scrolledTo.current || !id || !inFeed) return;
    scroller.current?.querySelector(`[data-short="${CSS.escape(id)}"]`)?.scrollIntoView();
    scrolledTo.current = true;
  }, [id, inFeed]);

  // The Short most on screen plays, and the address follows it.
  useEffect(() => {
    const root = scroller.current;
    if (!root) return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.find((entry) => entry.isIntersecting);
        const shown = (visible?.target as HTMLElement | undefined)?.dataset.short;
        if (shown) {
          setActiveId(shown);
          setCommentsOpen(false);
          window.history.replaceState(window.history.state, "", shortPath(shown));
        }
      },
      { root, threshold: 0.6 },
    );
    root.querySelectorAll("[data-short]").forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [queue.length]);

  // Near the end, the next page of the feed.
  const index = queue.findIndex((item) => item.id === activeId);
  useEffect(() => {
    if (index >= queue.length - 2 && feed.hasNextPage && !feed.isFetchingNextPage) {
      void feed.fetchNextPage();
    }
  }, [index, queue.length, feed]);

  const go = useCallback(
    (step: -1 | 1) => {
      const target = queue[index + step];
      if (!target) return;
      scroller.current
        ?.querySelector(`[data-short="${CSS.escape(target.id)}"]`)
        ?.scrollIntoView({ behavior: "smooth" });
    },
    [queue, index],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || !isForPlayer(event.target, event.key)) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        go(event.key === "ArrowDown" ? 1 : -1);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [go]);

  if (feed.isError && queue.length === 0) {
    return (
      <p role="alert" className="p-16 text-center text-ink-muted">
        Couldn't load Shorts.
      </p>
    );
  }
  if (feed.isFetched && queue.length === 0 && !single.isPending) {
    return <p className="p-16 text-center text-ink-muted">No Shorts yet.</p>;
  }

  const navButton =
    "grid size-12 place-items-center rounded-full bg-hover hover:bg-hover-strong disabled:opacity-40";
  return (
    <div className="relative">
      <h1 className="sr-only">Shorts</h1>
      <div
        ref={scroller}
        className="h-[calc(100dvh-3.5rem)] snap-y snap-mandatory overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {queue.map((video) => (
          <section
            key={video.id}
            data-short={video.id}
            aria-label={video.title}
            className="relative h-full snap-start snap-always px-4 py-4"
          >
            <ShortItem
              video={video}
              active={video.id === activeId}
              commentsOpen={commentsOpen}
              onComments={() => setCommentsOpen((open) => !open)}
            />
          </section>
        ))}
      </div>
      <div className="absolute top-1/2 right-6 hidden -translate-y-1/2 flex-col gap-4 lg:flex">
        <button
          type="button"
          aria-label="Previous Short"
          disabled={index <= 0}
          onClick={() => go(-1)}
          className={navButton}
        >
          <svg viewBox="0 0 24 24" className="size-6" fill="currentColor" aria-hidden>
            <path d="M12 8l-6 6 1.41 1.41L12 10.83l4.59 4.58L18 14z" />
          </svg>
        </button>
        <button
          type="button"
          aria-label="Next Short"
          disabled={index < 0 || index >= queue.length - 1}
          onClick={() => go(1)}
          className={navButton}
        >
          <svg viewBox="0 0 24 24" className="size-6" fill="currentColor" aria-hidden>
            <path d="M16.59 8.59 12 13.17 7.41 8.59 6 10l6 6 6-6z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
