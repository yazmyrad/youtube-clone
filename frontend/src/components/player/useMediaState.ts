import { useEffect, useState, type RefObject } from "react";

export interface MediaState {
  paused: boolean;
  ended: boolean;
  /** Playing was asked for, but there's no data yet: show a spinner. */
  waiting: boolean;
  currentTime: number;
  duration: number;
  /** Where the buffer ahead of the playhead ends. */
  bufferedEnd: number;
  volume: number;
  muted: boolean;
  playbackRate: number;
}

const INITIAL: MediaState = {
  paused: true,
  ended: false,
  waiting: false,
  currentTime: 0,
  duration: 0,
  bufferedEnd: 0,
  volume: 1,
  muted: false,
  playbackRate: 1,
};

const EVENTS = [
  "play",
  "pause",
  "playing",
  "waiting",
  "seeking",
  "seeked",
  "ended",
  "timeupdate",
  "durationchange",
  "loadedmetadata",
  "progress",
  "volumechange",
  "ratechange",
  "canplay",
  "emptied",
] as const;

export function readMediaState(video: HTMLVideoElement, waiting: boolean): MediaState {
  let bufferedEnd = 0;
  for (let i = 0; i < video.buffered.length; i++) {
    if (video.buffered.start(i) <= video.currentTime + 0.5) {
      bufferedEnd = Math.max(bufferedEnd, video.buffered.end(i));
    }
  }
  return {
    paused: video.paused,
    ended: video.ended,
    waiting,
    currentTime: video.currentTime || 0,
    duration: Number.isFinite(video.duration) ? video.duration : 0,
    bufferedEnd,
    volume: video.volume,
    muted: video.muted,
    playbackRate: video.playbackRate,
  };
}

/** The video element's state, kept current from its events. */
export function useMediaState(video: RefObject<HTMLVideoElement | null>): MediaState {
  const [state, setState] = useState<MediaState>(INITIAL);

  useEffect(() => {
    const element = video.current;
    if (!element) return undefined;
    let waiting = false;
    const listeners = new AbortController();
    const update = (event?: Event) => {
      if (event?.type === "waiting" || event?.type === "seeking") waiting = true;
      if (
        ["playing", "canplay", "seeked", "pause", "ended", "emptied"].includes(event?.type ?? "")
      ) {
        waiting = false;
      }
      setState(readMediaState(element, waiting && !element.paused));
    };
    for (const name of EVENTS) element.addEventListener(name, update, { signal: listeners.signal });
    update();
    return () => listeners.abort();
  }, [video]);

  return state;
}
