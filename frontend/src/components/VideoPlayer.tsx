import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
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

function fetchGrantFor(videoId: string) {
  return () => requestPlayback(api, videoId);
}

function playWithHlsJs(
  video: HTMLVideoElement,
  videoId: string,
  first: PlaybackGrant,
  Hls: typeof import("hls.js").default,
  onFailed: OnFailed,
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

export function VideoPlayer({ videoId, poster }: { videoId: string; poster?: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [failure, setFailure] = useState<PlayerFailure | null>(null);

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

    async function start(element: HTMLVideoElement) {
      const [grant, { default: Hls }] = await Promise.all([
        requestPlayback(api, videoId, request.signal),
        import("hls.js"),
      ]);
      if (closed) return;
      if (Hls.isSupported()) {
        stopPlayer = playWithHlsJs(element, videoId, grant, Hls, onFailed);
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
    <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-black">
      {/* Stays mounted under a failure, for the next video this player is given. */}
      <video
        ref={videoRef}
        poster={poster}
        controls={failure === null}
        autoPlay
        playsInline
        className="size-full"
      />
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
