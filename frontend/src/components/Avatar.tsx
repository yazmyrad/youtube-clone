import { useState } from "react";

/** Dark enough for white letters to read (WCAG AA), and distinct from one another. */
export const AVATAR_COLORS = [
  "#3949ab",
  "#5e35b1",
  "#00796b",
  "#c2185b",
  "#6d4c41",
  "#1976d2",
  "#2e7d32",
  "#00838f",
  "#d32f2f",
  "#ad1457",
  "#455a64",
  "#bf360c",
];

/** The same color for a channel everywhere, like YouTube's letter avatars. */
export function avatarColor(username: string): string {
  let hash = 0;
  for (const char of username.toLowerCase()) hash = (hash * 31 + char.codePointAt(0)!) >>> 0;
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]!;
}

/** The channel's picture, or its letter avatar when it has none (or the picture won't load).
 * Decorative: the name is always written next to it. */
export function Avatar({
  name,
  username,
  src,
  className = "size-9 text-sm",
}: {
  name: string;
  username: string;
  src?: string | null;
  /** Size and text size. */
  className?: string;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  if (src && failed !== src) {
    return (
      <img
        src={src}
        alt=""
        aria-hidden
        loading="lazy"
        onError={() => setFailed(src)}
        className={`shrink-0 rounded-full bg-hover object-cover ${className}`}
      />
    );
  }
  return (
    <span
      aria-hidden
      style={{ backgroundColor: avatarColor(username) }}
      className={`grid shrink-0 place-items-center rounded-full font-medium text-white uppercase ${className}`}
    >
      {Array.from(name.trim())[0] ?? "?"}
    </span>
  );
}
