/** Formatting for video cards, in YouTube's style: "4:05", "1.2K views", "3 days ago". */

export function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

const compact = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export function formatViews(count: number): string {
  if (count === 1) return "1 view";
  return `${compact.format(count)} views`;
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

const relative = new Intl.RelativeTimeFormat("en", { numeric: "always" });

export function formatAge(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000);
  for (const [unit, size] of UNITS) {
    if (seconds >= size) return relative.format(-Math.floor(seconds / size), unit);
  }
  return "just now";
}

export function formatSubscribers(count: number): string {
  if (count === 1) return "1 subscriber";
  return `${compact.format(count)} subscribers`;
}

/** A channel's page, YouTube style: "/@username". */
export function channelPath(username: string): string {
  return `/@${encodeURIComponent(username)}`;
}

export function playlistPath(playlistId: string): string {
  return `/playlist?list=${encodeURIComponent(playlistId)}`;
}

/** The watch page, inside a playlist: YouTube's "/watch?v=…&list=…". */
export function watchPath(videoId: string, playlistId?: string): string {
  const video = `/watch?v=${encodeURIComponent(videoId)}`;
  return playlistId ? `${video}&list=${encodeURIComponent(playlistId)}` : video;
}

export function videoCount(count: number): string {
  return count === 1 ? "1 video" : `${count.toLocaleString("en")} videos`;
}
