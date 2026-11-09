import { renderToString } from "react-dom/server";
import { expect, it } from "vitest";

import { CommentItem } from "./Comments";

const comment = (body: string) => ({
  id: "c1",
  body,
  created_at: "2026-01-02T03:04:05Z",
  author: { username: "ana", display_name: "Ana" },
});

it("shows a comment's markup as plain text", () => {
  const html = renderToString(<CommentItem comment={comment("<script>alert(1)</script>")} />);

  expect(html).toContain("&lt;script&gt;");
  expect(html).not.toContain("<script>");
});

it("names the author", () => {
  expect(renderToString(<CommentItem comment={comment("hi")} />)).toContain("ana");
});
