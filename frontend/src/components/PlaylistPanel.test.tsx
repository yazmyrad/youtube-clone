import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Playlist } from "../hooks/usePlaylists";
import { nextInPlaylist, PlaylistPanel } from "./PlaylistPanel";

const card = (id: string, title: string) => ({
  id,
  title,
  duration_seconds: 61,
  views_count: 3,
  published_at: "2026-01-02T03:04:05Z",
  thumbnail_url: `/thumbs/${id}.jpg`,
  channel: { username: "carol", display_name: "Carol" },
});

const playlist: Playlist = {
  id: "p1",
  title: "Rust picks",
  description: "",
  visibility: "public",
  channel: { username: "ana", display_name: "Ana Codes" },
  video_count: 3,
  thumbnail_url: "/thumbs/a.jpg",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  items: [card("a", "First"), card("b", "Second"), card("c", "Third")],
};

describe("nextInPlaylist", () => {
  it("is the following video", () => {
    expect(nextInPlaylist(playlist, "a")).toBe("b");
  });

  it("is nothing after the last one", () => {
    expect(nextInPlaylist(playlist, "c")).toBeNull();
  });

  it("is nothing for a video that isn't in the playlist", () => {
    expect(nextInPlaylist(playlist, "zzz")).toBeNull();
  });
});

describe("PlaylistPanel", () => {
  const html = renderToString(
    <MemoryRouter>
      <PlaylistPanel playlist={playlist} videoId="b" />
    </MemoryRouter>,
  );

  it("names the playlist and where the video is in it", () => {
    expect(html).toContain("Rust picks");
    expect(html).toContain("2 / 3");
    expect(html).toContain('href="/playlist?list=p1"');
  });

  it("links every video within the playlist and marks the current one", () => {
    expect(html).toContain('href="/watch?v=a&amp;list=p1"');
    expect(html).toContain('href="/watch?v=c&amp;list=p1"');
    expect(html.match(/aria-current="true"/g)).toHaveLength(1);
    expect(html).toMatch(
      /aria-current="true"[^>]*href="\/watch\?v=b&amp;list=p1"|href="\/watch\?v=b&amp;list=p1"[^>]*aria-current="true"/,
    );
  });
});
