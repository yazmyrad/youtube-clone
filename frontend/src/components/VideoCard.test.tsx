import type { ReactElement } from "react";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";

import { VideoGridCard, VideoRowCard, type VideoCardData } from "./VideoCard";

const video: VideoCardData = {
  id: "a7f3",
  title: "<b>Cats</b> & dogs",
  duration_seconds: 245,
  views_count: 1234,
  published_at: "2026-01-02T03:04:05Z",
  thumbnail_url: "/thumbs/a7f3.jpg?sig=x",
  channel: { username: "ana", display_name: "Ana" },
};

const render = (card: ReactElement) => renderToString(<MemoryRouter>{card}</MemoryRouter>);

it.each([
  ["grid", VideoGridCard],
  ["row", VideoRowCard],
])("the %s card links to the watch page and shows the details", (_, Card) => {
  const html = render(<Card video={video} />);

  expect(html).toContain('href="/watch?v=a7f3"');
  expect(html).toContain('src="/thumbs/a7f3.jpg?sig=x"');
  expect(html).toContain("4:05");
  expect(html).toContain("1.2K views");
  expect(html).toContain("Ana");
});

it("shows the title's markup as plain text", () => {
  const html = render(<VideoGridCard video={video} />);

  expect(html).toContain("&lt;b&gt;Cats&lt;/b&gt;");
  expect(html).not.toContain("<b>Cats");
});

it.each([
  ["grid", VideoGridCard],
  ["row", VideoRowCard],
])("the %s card links the channel name to the channel page", (_, Card) => {
  expect(render(<Card video={video} />)).toContain('href="/@ana"');
});

it("leaves the channel out on the channel's own page, and shows a badge", () => {
  const html = render(<VideoGridCard video={video} showChannel={false} badge="Private" />);

  expect(html).not.toContain('href="/@ana"');
  expect(html).not.toContain("Ana");
  expect(html).toContain("Private");
});
