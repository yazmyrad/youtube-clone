// Types only: a value import would pull hls.js into the bundle every page loads.
import type { ErrorDetails, ErrorTypes } from "hls.js";

import type { Api } from "./client";
import { errorMessage } from "./errors";
import type { components } from "./schema";

export type PlaybackGrant = components["schemas"]["PlaybackOut"];
export type PlayerFailure = "unavailable" | "unsupported" | "error";

export const RENEW_BEFORE_MS = 60_000;
/** Keeps a very short token lifetime from turning renewal into a busy loop. */
export const MIN_RENEW_DELAY_MS = 5_000;
export const RETRY_MS = 10_000;
export const MAX_FORBIDDEN_ROUNDS = 3;

const MANIFEST_LOAD_ERROR = "manifestLoadError" satisfies `${ErrorDetails}`;
const MEDIA_ERROR = "mediaError" satisfies `${ErrorTypes}`;

/** The server refused: the viewer has no access (any more), or the video is hidden or gone. */
export class PlaybackUnavailable extends Error {}

export async function requestPlayback(
  client: Api,
  videoId: string,
  signal?: AbortSignal,
): Promise<PlaybackGrant> {
  const { data, error, response } = await client.POST("/api/videos/{video_id}/playback", {
    params: { path: { video_id: videoId } },
    signal,
  });
  if (data) return data;
  if (response.status === 404) throw new PlaybackUnavailable(errorMessage(error));
  throw new Error(errorMessage(error));
}

const TOKEN_SEGMENT = /\/hls\/([^/]+)\//;

export function tokenOf(url: string): string | null {
  return TOKEN_SEGMENT.exec(url)?.[1] ?? null;
}

/** hls.js keeps the URLs it resolved from the first playlist, each with the token it had then. */
export function withToken(url: string, token: string): string {
  return url.replace(TOKEN_SEGMENT, () => `/hls/${token}/`);
}

export interface TokenRenewal {
  start(grant: PlaybackGrant): void;
  /** The video started playing: catch up on a renewal skipped while it was paused. */
  onPlay(): void;
  /** A fragment arrived, so the current token works. */
  onProgress(): void;
  /** Storage refused a request. `onRenewed` runs after the new token, if loading has stopped. */
  handleForbidden(onRenewed?: (grant: PlaybackGrant) => void): void;
  stop(): void;
}

interface RenewalOptions {
  fetchGrant: () => Promise<PlaybackGrant>;
  isPaused: () => boolean;
  onGrant: (grant: PlaybackGrant) => void;
  onFailed: (failure: PlayerFailure) => void;
}

/** Every renewal goes through `/playback`, so each one repeats the full permission check. */
export function createTokenRenewal(options: RenewalOptions): TokenRenewal {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;
  let due = false;
  let renewing = false;
  let forbiddenRounds = 0;
  let resume: ((grant: PlaybackGrant) => void) | undefined;

  function schedule(delay: number) {
    clearTimeout(timer);
    timer = setTimeout(onTimer, delay);
  }

  function scheduleBeforeExpiry(grant: PlaybackGrant) {
    const remaining = Date.parse(grant.expires_at) - Date.now();
    schedule(Math.max(MIN_RENEW_DELAY_MS, remaining - RENEW_BEFORE_MS));
  }

  // A paused tab shouldn't ask for tokens forever. Stopped loading still needs one, though.
  function onTimer() {
    if (options.isPaused() && !resume) due = true;
    else void renew();
  }

  function stop() {
    stopped = true;
    clearTimeout(timer);
  }

  function fail(failure: PlayerFailure) {
    stop();
    options.onFailed(failure);
  }

  async function renew() {
    if (renewing || stopped) return;
    renewing = true;
    due = false;
    try {
      const grant = await options.fetchGrant();
      renewing = false;
      if (stopped) return;
      options.onGrant(grant);
      scheduleBeforeExpiry(grant);
      const resumeLoading = resume;
      resume = undefined;
      resumeLoading?.(grant);
    } catch (failure) {
      renewing = false;
      if (stopped) return;
      if (failure instanceof PlaybackUnavailable) fail("unavailable");
      else schedule(RETRY_MS);
    }
  }

  return {
    start: scheduleBeforeExpiry,
    onPlay() {
      if (due) void renew();
    },
    onProgress() {
      forbiddenRounds = 0;
    },
    handleForbidden(onRenewed) {
      if (stopped) return;
      if (onRenewed) resume = onRenewed;
      if (renewing) return;
      // Storage also answers 403 for a file that doesn't exist, which no new token can fix.
      forbiddenRounds += 1;
      if (forbiddenRounds > MAX_FORBIDDEN_ROUNDS) fail("error");
      else void renew();
    },
    stop,
  };
}

interface HlsErrorInfo {
  fatal: boolean;
  type: string;
  details: string;
  response?: { code?: number };
}

interface HlsControls {
  loadSource(url: string): void;
  startLoad(position?: number): void;
  recoverMediaError(): void;
}

export function createHlsErrorHandler(
  hls: HlsControls,
  media: { currentTime: number },
  renewal: Pick<TokenRenewal, "handleForbidden">,
  onFailed: (failure: PlayerFailure) => void,
) {
  let triedMediaRecovery = false;

  return (error: HlsErrorInfo) => {
    if (error.response?.code === 403) {
      renewal.handleForbidden(
        error.fatal
          ? (grant) => {
              if (error.details === MANIFEST_LOAD_ERROR) hls.loadSource(grant.url);
              else hls.startLoad(media.currentTime);
            }
          : undefined,
      );
      return;
    }
    if (!error.fatal) return;
    if (error.type === MEDIA_ERROR && !triedMediaRecovery) {
      triedMediaRecovery = true;
      hls.recoverMediaError();
      return;
    }
    onFailed("error");
  };
}
