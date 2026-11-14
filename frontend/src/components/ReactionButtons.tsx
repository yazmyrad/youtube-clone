import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { nextReaction, useReaction, type Reaction } from "../hooks/useReaction";
import type { VideoDetails } from "../hooks/useVideo";
import { ThumbDownIcon, ThumbUpIcon } from "./icons";

export function ReactionButtons({ video }: { video: VideoDetails }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const react = useReaction(video.id);

  function press(pressed: Reaction) {
    if (!user) {
      void navigate(`/login?next=${encodeURIComponent(pathname + search)}`);
      return;
    }
    react.mutate(nextReaction(video.my_reaction, pressed));
  }

  const button = "flex h-9 items-center gap-2 px-4 text-sm font-medium hover:bg-hover-strong";
  const active = (reaction: Reaction) => (video.my_reaction === reaction ? "text-accent" : "");

  return (
    <div className="flex shrink-0 flex-col items-end gap-1">
      <div className="flex overflow-hidden rounded-full bg-hover">
        <button
          type="button"
          aria-label="Like"
          aria-pressed={video.my_reaction === "like"}
          disabled={react.isPending}
          onClick={() => press("like")}
          className={`${button} border-r border-line ${active("like")}`}
        >
          <ThumbUpIcon />
          {video.likes_count.toLocaleString()}
        </button>
        <button
          type="button"
          aria-label="Dislike"
          aria-pressed={video.my_reaction === "dislike"}
          disabled={react.isPending}
          onClick={() => press("dislike")}
          className={`${button} ${active("dislike")}`}
        >
          <ThumbDownIcon />
        </button>
      </div>
      {react.isError && (
        <p role="alert" className="text-xs text-danger">
          {react.error.message}
        </p>
      )}
    </div>
  );
}
