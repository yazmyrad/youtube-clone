import { useEffect, useState, type RefObject } from "react";

import { api } from "../../api/client";
import {
  PlaybackUnavailable,
  createHlsErrorHandler,
  createTokenRenewal,
  requestPlayback,
  tokenOf,
  withToken,
  type PlaybackGrant,
  type PlayerFailure,
} from "../../api/playback";
import type { Quality } from "./PlayerControls";

export const FAILURE_TEXT: Record<PlayerFailure, string> = {
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
      // The one asked for, -1 for Auto: currentLevel can name the old one until it switches.
      selected: hls.manualLevel ?? (hls.autoLevelEnabled ? -1 : hls.currentLevel),
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

/** Loads `videoId` into `video` with a playback grant: hls.js where it works, the browser's
 * own HLS elsewhere. Off while `enabled` is false, as for a Short scrolled out of view. */
export function usePlayback(
  videoRef: RefObject<HTMLVideoElement | null>,
  videoId: string,
  enabled = true,
): { failure: PlayerFailure | null; quality: Quality | null } {
  const [failure, setFailure] = useState<PlayerFailure | null>(null);
  const [quality, setQuality] = useState<Quality | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !enabled) return undefined;

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
  }, [videoRef, videoId, enabled]);

  return { failure, quality };
}
