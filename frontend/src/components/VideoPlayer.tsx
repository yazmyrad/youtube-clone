import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import { useViewHeartbeat } from "../hooks/useViewHeartbeat";
import { PlayerControls, type Quality } from "./player/PlayerControls";
import { useMediaState } from "./player/useMediaState";
import {
  PlaybackUnavailable,
  createHlsErrorHandler,
  createTokenRenewal,
  requestPlayback,
  tokenOf,
  withToken,
  type PlaybackGrant,
  type PlayerFailure,
} from "../api/playback";

const FAILURE_TEXT: Record<PlayerFailure, string> = {
  unavailable: "This video isn't available.",
  unsupported: "Your browser can't play this video.",
  error: "The video couldn't be played. Please try again later.",
};

type Stop = () => void;
type OnFailed = (failure: PlayerFailure) => void;
type OnQuality = (quality: Quality) => void;

function fetchGrantFor(videoId: string) {
  return () => requestPlayback(api, videoId);
}

function playWithHlsJs(
  video: HTMLVideoElement,
  videoId: string,
  first: PlaybackGrant,
  Hls: typeof import("hls.js").default,
  onFailed: OnFailed,
  onQuality: OnQuality,
): Stop {
  let token = tokenOf(first.url) ?? "";
  const hls = new Hls({
    // hls.js only opens a request that this hook left unopened.
    xhrSetup: (xhr, url) => xhr.open("GET", withToken(url, token), true),
  });
  const renewal = createTokenRenewal({
    fetchGrant: fetchGrantFor(videoId),
    isPaused: () => video.paused,
    onGrant: (grant) => {
      token = tokenOf(grant.url) ?? token;
    },
    onFailed,
  });
  const onPlay = () => renewal.onPlay();
  const handleError = createHlsErrorHandler(hls, video, renewal, onFailed);

  // The renditions for the settings menu, and which one Auto is playing.
  const reportQuality = () => {
    const levels = hls.levels ?? [];
    const playing = levels[hls.currentLevel]?.height ?? null;
    onQuality({
      heights: levels.map((level) => level.height),
      selected: hls.autoLevelEnabled ? -1 : hls.currentLevel,
      playing,
      select: (index) => {
        hls.currentLevel = index;
        reportQuality();
      },
    });
  };
  hls.on(Hls.Events.MANIFEST_PARSED, reportQuality);
  hls.on(Hls.Events.LEVEL_SWITCHED, reportQuality);
  hls.on(Hls.Events.ERROR, (_event, data) => handleError(data));
  hls.on(Hls.Events.FRAG_LOADED, () => renewal.onProgress());
  video.addEventListener("play", onPlay);
  hls.loadSource(first.url);
  hls.attachMedia(video);
  renewal.start(first);

  return () => {
    renewal.stop();
    video.removeEventListener("play", onPlay);
    hls.destroy();
  };
}

/** Safari on iOS has no MediaSource, but plays HLS itself. Its requests can't be rewritten, so
 * an expired token surfaces as an error, and the source is replaced to carry on from there. */
function playNatively(
  video: HTMLVideoElement,
  videoId: string,
  first: PlaybackGrant,
  onFailed: OnFailed,
): Stop {
  const listeners = new AbortController();
  const { signal } = listeners;
  const renewal = createTokenRenewal({
    fetchGrant: fetchGrantFor(videoId),
    isPaused: () => video.paused,
    onGrant: () => {},
    onFailed,
  });

  video.addEventListener("playing", () => renewal.onProgress(), { signal });
  video.addEventListener(
    "error",
    () => {
      const position = video.currentTime;
      renewal.handleForbidden((grant) => {
        video.addEventListener("loadedmetadata", () => (video.currentTime = position), {
          once: true,
          signal,
        });
        video.src = grant.url;
        void video.play().catch(() => {});
      });
    },
    { signal },
  );
  video.src = first.url;

  return () => {
    renewal.stop();
    listeners.abort();
    video.removeAttribute("src");
    video.load();
  };
}

export function VideoPlayer({
  videoId,
  poster,
  onEnded,
  onNext,
  theater = false,
  onTheater,
}: {
  videoId: string;
  poster?: string;
  /** Called when the video plays to its end, as for moving on in a playlist. */
  onEnded?: () => void;
  /** The Next button (and SHIFT+N); none without it. */
  onNext?: () => void;
  /** Theater mode: the player takes the page's width. */
  theater?: boolean;
  onTheater?: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [failure, setFailure] = useState<PlayerFailure | null>(null);
  const [quality, setQuality] = useState<Quality | null>(null);
  const media = useMediaState(videoRef);
  useViewHeartbeat(videoRef, videoId);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return undefined;

    const request = new AbortController();
    let stopPlayer: Stop | undefined;
    let closed = false;

    const close = () => {
      closed = true;
      request.abort();
      stopPlayer?.();
      stopPlayer = undefined;
    };
    const onFailed: OnFailed = (reason) => {
      close();
      setFailure(reason);
    };

    setFailure(null);
    setQuality(null);

    async function start(element: HTMLVideoElement) {
      const [grant, { default: Hls }] = await Promise.all([
        requestPlayback(api, videoId, request.signal),
        import("hls.js"),
      ]);
      if (closed) return;
      if (Hls.isSupported()) {
        stopPlayer = playWithHlsJs(element, videoId, grant, Hls, onFailed, setQuality);
      } else if (element.canPlayType("application/vnd.apple.mpegurl")) {
        stopPlayer = playNatively(element, videoId, grant, onFailed);
      } else {
        onFailed("unsupported");
      }
    }

    start(video).catch((reason: unknown) => {
      if (!closed) onFailed(reason instanceof PlaybackUnavailable ? "unavailable" : "error");
    });

    return close;
  }, [videoId]);

  return (
    <div
      ref={containerRef}
      data-player
      className={`relative w-full overflow-hidden bg-black select-none ${
        theater ? "h-[min(56.25vw,calc(100vh-169px))]" : "aspect-video rounded-xl"
      }`}
    >
      {/* Stays mounted under a failure, for the next video this player is given. */}
      <video
        ref={videoRef}
        poster={poster}
        autoPlay
        playsInline
        onEnded={onEnded}
        className="size-full"
      />
      {failure === null && (
        <PlayerControls
          video={videoRef}
          container={containerRef}
          state={media}
          quality={quality}
          theater={theater}
          onTheater={onTheater}
          onNext={onNext}
        />
      )}
      {failure && (
        <p
          role="alert"
          className="absolute inset-0 grid place-items-center bg-black p-6 text-center text-white"
        >
          {FAILURE_TEXT[failure]}
        </p>
      )}
    </div>
  );
}
