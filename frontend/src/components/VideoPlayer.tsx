import { useRef } from "react";

import { useViewHeartbeat } from "../hooks/useViewHeartbeat";
import { PlayerControls } from "./player/PlayerControls";
import { FAILURE_TEXT, usePlayback } from "./player/usePlayback";
import { useMediaState } from "./player/useMediaState";

export function VideoPlayer({
  videoId,
  poster,
  onEnded,
  onNext,
  theater = false,
  onTheater,
}: {
  videoId: string;
  poster?: string;
  /** Called when the video plays to its end, as for moving on in a playlist. */
  onEnded?: () => void;
  /** The Next button (and SHIFT+N); none without it. */
  onNext?: () => void;
  /** Theater mode: the player takes the page's width. */
  theater?: boolean;
  onTheater?: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { failure, quality } = usePlayback(videoRef, videoId);
  const media = useMediaState(videoRef);
  useViewHeartbeat(videoRef, videoId);

  return (
    <div
      ref={containerRef}
      data-player
      // Focusable, so it can hold the keys that would otherwise scroll the page.
      tabIndex={-1}
      className={`relative w-full overflow-hidden bg-black outline-none select-none ${
        theater ? "h-[min(56.25vw,calc(100vh-169px))]" : "aspect-video rounded-xl"
      }`}
    >
      {/* Stays mounted under a failure, for the next video this player is given. */}
      <video
        ref={videoRef}
        poster={poster}
        autoPlay
        playsInline
        onEnded={onEnded}
        className="size-full"
      />
      {failure === null && (
        <PlayerControls
          video={videoRef}
          container={containerRef}
          state={media}
          quality={quality}
          theater={theater}
          onTheater={onTheater}
          onNext={onNext}
        />
      )}
      {failure && (
        <p
          role="alert"
          className="absolute inset-0 grid place-items-center bg-black p-6 text-center text-white"
        >
          {FAILURE_TEXT[failure]}
        </p>
      )}
    </div>
  );
}
