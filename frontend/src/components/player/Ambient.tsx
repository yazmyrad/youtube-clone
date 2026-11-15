import { useEffect, useRef, useState, type RefObject } from "react";

export const AMBIENT_KEY = "player.ambient";

/** A tiny picture is all a glow this blurred needs, and it costs next to nothing to draw. */
const WIDTH = 32;
const HEIGHT = 18;
/** How often the glow catches up with the video while it plays. */
const STEP_MS = 100;
/** Each step blends this much of the new frame in, so the glow drifts rather than flickers. */
const BLEND = 0.15;

/** YouTube's Ambient mode setting, on unless turned off, and remembered. */
export function useAmbientSetting(): [boolean, () => void] {
  const [on, setOn] = useState(() => {
    try {
      return localStorage.getItem(AMBIENT_KEY) !== "0";
    } catch {
      return true;
    }
  });
  const toggle = () =>
    setOn((value) => {
      try {
        localStorage.setItem(AMBIENT_KEY, value ? "0" : "1");
      } catch {
        // Not remembered, then.
      }
      return !value;
    });
  return [on, toggle];
}

/**
 * Ambient mode: the video's colors, blurred, glowing around the player and following it as it
 * plays. A canvas behind the player, painted from the video's frames.
 */
export function AmbientGlow({ video }: { video: RefObject<HTMLVideoElement | null> }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = video.current;
    const context = canvas.current?.getContext("2d");
    if (!element || !context) return undefined;

    const paint = (alpha: number) => {
      // Nothing to show before the first frame has loaded.
      if (element.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
      context.globalAlpha = alpha;
      context.drawImage(element, 0, 0, WIDTH, HEIGHT);
    };

    let frame = 0;
    let last = 0;
    const loop = (now: number) => {
      if (now - last >= STEP_MS) {
        last = now;
        paint(BLEND);
      }
      frame = requestAnimationFrame(loop);
    };
    const start = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(loop);
    };
    const stop = () => cancelAnimationFrame(frame);
    // A jump (a seek, a new video, the first frame) shows the new picture at once.
    const jump = () => paint(1);

    const events: [string, () => void][] = [
      ["playing", start],
      ["pause", stop],
      ["ended", stop],
      ["emptied", stop],
      ["loadeddata", jump],
      ["seeked", jump],
    ];
    for (const [name, handler] of events) element.addEventListener(name, handler);
    jump();
    if (!element.paused) start();
    return () => {
      stop();
      for (const [name, handler] of events) element.removeEventListener(name, handler);
    };
  }, [video]);

  return (
    <canvas
      ref={canvas}
      width={WIDTH}
      height={HEIGHT}
      aria-hidden
      data-ambient
      className="pointer-events-none absolute inset-0 -z-10 size-full scale-[1.15] opacity-80 blur-[80px] saturate-150"
    />
  );
}
