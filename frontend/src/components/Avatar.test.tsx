import { renderToString } from "react-dom/server";
import { expect, it } from "vitest";

import { Avatar, AVATAR_COLORS, avatarColor } from "./Avatar";

it("gives a channel the same color every time, whatever the case", () => {
  expect(avatarColor("codebytes")).toBe(avatarColor("CodeBytes"));
  expect(AVATAR_COLORS).toContain(avatarColor("codebytes"));
});

it("spreads channels over the colors", () => {
  const names = Array.from({ length: 60 }, (_, i) => `channel_${i}`);
  expect(new Set(names.map(avatarColor)).size).toBeGreaterThan(AVATAR_COLORS.length / 2);
});

it("shows the first letter, decoratively", () => {
  const html = renderToString(<Avatar name=" ana" username="ana" />);

  expect(html).toContain(">a<");
  expect(html).toContain('aria-hidden="true"');
  expect(html).toContain(`background-color:${avatarColor("ana")}`);
});

it("handles a name that starts with an emoji as one letter", () => {
  expect(renderToString(<Avatar name="🎬 Studio" username="studio" />)).toContain(">🎬<");
});
