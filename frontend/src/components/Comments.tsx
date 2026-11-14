import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import {
  MAX_COMMENT_LENGTH,
  cleanComment,
  useAddComment,
  useComments,
  type Comment,
} from "../hooks/useComments";
import type { VideoDetails } from "../hooks/useVideo";
import { Avatar } from "./Avatar";
import { formatAge } from "./format";

export function CommentItem({ comment }: { comment: Comment }) {
  return (
    <li className="flex gap-3">
      <Avatar
        name={comment.author.display_name}
        username={comment.author.username}
        className="size-10"
      />
      <div className="min-w-0">
        <p className="text-xs">
          <span className="font-medium">@{comment.author.username}</span>{" "}
          <time
            dateTime={comment.created_at}
            title={new Date(comment.created_at).toLocaleString()}
            className="text-ink-muted"
          >
            {formatAge(comment.created_at)}
          </time>
        </p>
        <p className="mt-1 text-sm wrap-anywhere whitespace-pre-wrap">{comment.body}</p>
      </div>
    </li>
  );
}

function CommentForm({ videoId }: { videoId: string }) {
  const { user } = useAuth();
  const { pathname, search } = useLocation();
  const add = useAddComment(videoId);
  const [text, setText] = useState("");
  const body = cleanComment(text);

  if (!user) {
    return (
      <Link
        to={`/login?next=${encodeURIComponent(pathname + search)}`}
        className="text-sm font-medium text-accent"
      >
        Sign in to comment
      </Link>
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (body === null) return;
    add.mutate(body, { onSuccess: () => setText("") });
  }

  return (
    <form onSubmit={submit} className="flex gap-3">
      <Avatar name={user.display_name} username={user.username} className="size-10" />
      <div className="min-w-0 flex-1">
        <textarea
          aria-label="Add a comment"
          placeholder="Add a comment..."
          rows={1}
          maxLength={MAX_COMMENT_LENGTH}
          value={text}
          onChange={(event) => setText(event.target.value)}
          className="w-full resize-y border-b border-line bg-transparent py-1 text-sm outline-none focus:border-ink"
        />
        {add.isError && (
          <p role="alert" className="mt-1 text-sm text-red-700">
            {add.error.message}
          </p>
        )}
        <div className="mt-2 flex justify-end">
          <button
            type="submit"
            disabled={body === null || add.isPending}
            className="h-9 rounded-full bg-accent px-4 text-sm font-medium text-white hover:opacity-90 disabled:bg-hover disabled:text-ink-muted"
          >
            Comment
          </button>
        </div>
      </div>
    </form>
  );
}

export function Comments({ video }: { video: VideoDetails }) {
  const comments = useComments(video.id);
  const items = comments.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <section className="mt-6">
      <h2 className="mb-4 text-xl font-semibold">
        {video.comments_count.toLocaleString("en")}{" "}
        {video.comments_count === 1 ? "Comment" : "Comments"}
      </h2>
      <CommentForm videoId={video.id} />
      {comments.isError && (
        <p role="alert" className="mt-4 text-sm text-red-700">
          Couldn't load the comments.
        </p>
      )}
      <ul className="mt-6 flex flex-col gap-5">
        {items.map((comment) => (
          <CommentItem key={comment.id} comment={comment} />
        ))}
      </ul>
      {comments.hasNextPage && (
        <button
          type="button"
          disabled={comments.isFetchingNextPage}
          onClick={() => void comments.fetchNextPage()}
          className="mt-3 h-9 rounded-full px-4 text-sm font-medium text-accent hover:bg-accent-soft disabled:opacity-50"
        >
          Load more
        </button>
      )}
    </section>
  );
}
