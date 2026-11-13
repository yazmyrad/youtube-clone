import { useEffect, type RefObject } from "react";

import { api } from "../api/client";
import {
  HEARTBEAT_MS,
  sendView,
  SETTLED_AFTER_SECONDS,
  SETTLED_HEARTBEAT_MS,
  WatchTracker,
} from "../api/views";

/** Reports playback to the server while `video` plays, and when it pauses or ends: the
 * server counts the view and keeps the viewer's place in their history. */
export function useViewHeartbeat(video: RefObject<HTMLVideoElement | null>, videoId: string) {
  useEffect(() => {
    const element = video.current;
    if (!element) return undefined;
    const tracker = new WatchTracker();
    let sentAt = -1;

    const send = () => {
      // Nothing new since the last report.
      if (element.currentTime === sentAt) return;
      sentAt = element.currentTime;
      sendView(api, videoId, tracker.watched, element.currentTime).catch(() => {});
    };
    const listeners = new AbortController();
    const on = (event: string, handler: () => void) =>
      element.addEventListener(event, handler, { signal: listeners.signal });
    on("timeupdate", () => tracker.update(element.currentTime));
    on("seeked", () => tracker.seeked(element.currentTime));
    on("pause", send);
    on("ended", send);
    let lastTick = 0;
    const timer = window.setInterval(() => {
      if (element.paused) return;
      lastTick += HEARTBEAT_MS;
      // Once the view is settled, slow down: the reports only keep the history's place.
      const settled = tracker.watched >= SETTLED_AFTER_SECONDS;
      if (settled && lastTick < SETTLED_HEARTBEAT_MS) return;
      lastTick = 0;
      send();
    }, HEARTBEAT_MS);

    return () => {
      window.clearInterval(timer);
      listeners.abort();
      // Also after only seeking: the history keeps the place.
      if (tracker.watched > 0 || element.currentTime > 0) send();
    };
  }, [video, videoId]);
}
