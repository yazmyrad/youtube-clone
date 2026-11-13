import { useEffect, type RefObject } from "react";

import { api } from "../api/client";
import { HEARTBEAT_MS, sendView, WatchTracker } from "../api/views";

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
    const timer = window.setInterval(() => {
      if (!element.paused) send();
    }, HEARTBEAT_MS);

    return () => {
      window.clearInterval(timer);
      listeners.abort();
      if (tracker.watched > 0) send();
    };
  }, [video, videoId]);
}
