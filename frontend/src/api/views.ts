import type { Api } from "./client";

/** How often a playing video reports, in milliseconds. */
export const HEARTBEAT_MS = 10_000;

/** Seconds actually played: forward steps between time updates, so seeking ahead or
 * scrubbing doesn't count, and neither does sitting paused. */
export class WatchTracker {
  watched = 0;
  private last: number | null = null;

  update(currentTime: number): void {
    if (this.last !== null) {
      const step = currentTime - this.last;
      // Time updates come a few times a second; a bigger jump is a seek.
      if (step > 0 && step < 2) this.watched += step;
    }
    this.last = currentTime;
  }

  seeked(currentTime: number): void {
    this.last = currentTime;
  }
}

/** Best effort: a lost heartbeat only delays a view or a history update. */
export async function sendView(
  client: Api,
  videoId: string,
  watchedSeconds: number,
  positionSeconds: number,
): Promise<void> {
  await client.POST("/api/videos/{video_id}/view", {
    params: { path: { video_id: videoId } },
    body: {
      watched_seconds: Math.min(86_400, Math.floor(watchedSeconds)),
      position_seconds: Math.min(86_400, Math.max(0, Math.floor(positionSeconds))),
    },
  });
}
