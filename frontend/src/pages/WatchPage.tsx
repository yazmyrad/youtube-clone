import { useSearchParams } from "react-router-dom";

import { ReactionButtons } from "../components/ReactionButtons";
import { VideoPlayer } from "../components/VideoPlayer";
import { statusMessage, useVideo, VideoNotFound, type VideoDetails } from "../hooks/useVideo";
import { NotFoundPage } from "./NotFoundPage";

function Details({ video }: { video: VideoDetails }) {
  const published = video.published_at ?? video.created_at;
  return (
    <>
      <h1 className="mt-3 text-xl font-semibold wrap-anywhere">{video.title}</h1>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span
            aria-hidden
            className="grid size-10 shrink-0 place-items-center rounded-full bg-accent font-medium text-white"
          >
            {video.channel.display_name.charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium">{video.channel.display_name}</p>
            <p className="truncate text-xs text-ink-muted">@{video.channel.username}</p>
          </div>
        </div>
        {video.status === "ready" && <ReactionButtons video={video} />}
      </div>
      <div className="mt-3 rounded-xl bg-hover p-3 text-sm">
        <p className="font-medium">
          {video.views_count.toLocaleString()} views · {new Date(published).toLocaleDateString()}
        </p>
        {video.description && <p className="mt-2 wrap-anywhere whitespace-pre-wrap">{video.description}</p>}
      </div>
    </>
  );
}

function Watch({ videoId }: { videoId: string }) {
  const video = useVideo(videoId);

  if (video.isError) {
    if (video.error instanceof VideoNotFound) return <NotFoundPage />;
    return (
      <p role="alert" className="p-6 text-center text-sm text-red-700">
        Couldn't load this video.
      </p>
    );
  }

  const message = video.data ? statusMessage(video.data.status) : null;
  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      {video.isPending && <div className="aspect-video w-full rounded-xl bg-hover" />}
      {message !== null && (
        <div className="grid aspect-video w-full place-items-center rounded-xl bg-black p-6 text-center text-white">
          {message}
        </div>
      )}
      {video.data?.status === "ready" && (
        <VideoPlayer videoId={videoId} poster={video.data.thumbnail_url ?? undefined} />
      )}
      {video.data && <Details video={video.data} />}
    </div>
  );
}

export function WatchPage() {
  const [params] = useSearchParams();
  const videoId = params.get("v");
  if (!videoId) return <NotFoundPage />;
  // A new video starts from a clean page, not with the last one's details on screen.
  return <Watch key={videoId} videoId={videoId} />;
}
