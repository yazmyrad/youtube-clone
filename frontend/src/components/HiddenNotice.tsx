import { useAuth } from "../hooks/useAuth";
import { isModerator, useDecide } from "../hooks/useModeration";
import type { VideoDetails } from "../hooks/useVideo";

/** In place of the player on a hidden video. Only its owner and moderators get this far;
 * moderators can bring it back. */
export function HiddenNotice({ video }: { video: VideoDetails }) {
  const { user } = useAuth();
  const decide = useDecide();
  return (
    <div className="grid aspect-video w-full place-items-center rounded-xl bg-black p-6 text-center text-white">
      <div className="max-w-md space-y-3">
        <p className="text-lg font-medium">This video was hidden by a moderator.</p>
        {video.hidden_reason && (
          <p className="text-sm text-white/80 wrap-anywhere">Reason: {video.hidden_reason}</p>
        )}
        {isModerator(user?.role) && (
          <button
            type="button"
            disabled={decide.isPending}
            onClick={() => decide.mutate({ kind: "restore", videoId: video.id })}
            className="rounded-full bg-white px-4 py-2 text-sm font-medium text-black hover:opacity-85 disabled:opacity-60"
          >
            Restore video
          </button>
        )}
        {decide.isError && (
          <p role="alert" className="text-sm text-red-300">
            {decide.error.message}
          </p>
        )}
      </div>
    </div>
  );
}
