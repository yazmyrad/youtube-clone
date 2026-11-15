import { useRef } from "react";

import { useViewHeartbeat } from "../hooks/useViewHeartbeat";
import { useDarkTheme } from "../theme";
import { AmbientGlow, useAmbientSetting } from "./player/Ambient";
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
  // As on YouTube, Ambient mode belongs to the dark theme: a glow on white would only smudge.
  const dark = useDarkTheme();
  const [ambientOn, toggleAmbient] = useAmbientSetting();

  return (
    // No stacking context of its own: the glow's negative z-index puts it behind the page's
    // text, not only behind the player, so it lights the page without tinting the title.
    <div className="relative">
      {dark && ambientOn && failure === null && <AmbientGlow video={videoRef} />}
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
            ambient={dark ? { on: ambientOn, onToggle: toggleAmbient } : undefined}
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
    </div>
  );
}
