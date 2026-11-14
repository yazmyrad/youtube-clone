import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

import { formatDuration } from "../format";
import {
  CheckGlyph,
  ChevronGlyph,
  DefaultViewGlyph,
  ExitFullscreenGlyph,
  ForwardGlyph,
  FullscreenGlyph,
  NextGlyph,
  PauseGlyph,
  PlayGlyph,
  ReplayGlyph,
  RewindGlyph,
  SettingsGlyph,
  TheaterGlyph,
  VolumeHighGlyph,
  VolumeLowGlyph,
  VolumeOffGlyph,
} from "./icons";
import { actionFor, clamp, isForPlayer, nextSpeed, SPEEDS, type PlayerAction } from "./shortcuts";
import type { MediaState } from "./useMediaState";

/** The renditions hls.js can play, and the one chosen; -1 is Auto. */
export interface Quality {
  heights: number[];
  selected: number;
  /** What Auto is playing right now. */
  playing: number | null;
  select: (index: number) => void;
}

interface Props {
  video: RefObject<HTMLVideoElement | null>;
  container: RefObject<HTMLDivElement | null>;
  state: MediaState;
  quality: Quality | null;
  theater?: boolean;
  onTheater?: () => void;
  onNext?: () => void;
}

/** Idle this long while playing, and the controls and the cursor go. */
export const HIDE_AFTER_MS = 3000;
const VOLUME_KEY = "player.volume";

type Menu = null | "main" | "speed" | "quality";
interface Flash {
  id: number;
  content: ReactNode;
  side?: "left" | "right";
}

function speedLabel(rate: number): string {
  return rate === 1 ? "Normal" : String(rate);
}

export function qualityLabel(quality: Quality | null): string {
  if (!quality || quality.selected < 0) {
    return quality?.playing ? `Auto (${quality.playing}p)` : "Auto";
  }
  return `${quality.heights[quality.selected]}p`;
}

function ControlButton({
  label,
  onClick,
  children,
  pressed,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      onClick={onClick}
      className="grid size-12 shrink-0 place-items-center p-2.5 text-white opacity-90 hover:opacity-100 focus-visible:outline-2 focus-visible:outline-white"
    >
      {children}
    </button>
  );
}

function ProgressBar({
  state,
  onSeek,
  onScrub,
}: {
  state: MediaState;
  onSeek: (time: number) => void;
  onScrub: (scrubbing: boolean) => void;
}) {
  const bar = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const { duration, currentTime, bufferedEnd } = state;
  const percent = (time: number) => (duration > 0 ? clamp(time / duration, 0, 1) * 100 : 0);

  const timeAt = (clientX: number) => {
    const rect = bar.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || duration <= 0) return 0;
    return clamp((clientX - rect.left) / rect.width, 0, 1) * duration;
  };

  return (
    <div
      ref={bar}
      role="slider"
      aria-label="Seek"
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={Math.round(currentTime)}
      aria-valuetext={`${formatDuration(currentTime)} of ${formatDuration(duration)}`}
      className="group/bar relative mx-3 flex h-4 cursor-pointer touch-none items-end"
      onPointerMove={(event) => {
        setHover(timeAt(event.clientX));
        if (dragging) onSeek(timeAt(event.clientX));
      }}
      onPointerLeave={() => setHover(null)}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture?.(event.pointerId);
        setDragging(true);
        onScrub(true);
        onSeek(timeAt(event.clientX));
      }}
      onPointerUp={(event) => {
        event.currentTarget.releasePointerCapture?.(event.pointerId);
        setDragging(false);
        onScrub(false);
      }}
    >
      {hover !== null && (
        <span
          className="pointer-events-none absolute bottom-6 -translate-x-1/2 rounded bg-black/80 px-2 py-0.5 text-xs font-medium text-white"
          style={{ left: `${percent(hover)}%` }}
        >
          {formatDuration(hover)}
        </span>
      )}
      <div
        className={`relative w-full bg-white/20 transition-[height] ${dragging ? "h-[5px]" : "h-[3px] group-hover/bar:h-[5px]"}`}
      >
        <div
          className="absolute inset-y-0 left-0 bg-white/40"
          style={{ width: `${percent(bufferedEnd)}%` }}
        />
        {hover !== null && (
          <div
            className="absolute inset-y-0 left-0 bg-white/50"
            style={{ width: `${percent(hover)}%` }}
          />
        )}
        <div
          className="absolute inset-y-0 left-0 bg-[#f00]"
          style={{ width: `${percent(currentTime)}%` }}
        />
        <div
          className={`absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#f00] transition-transform ${dragging ? "scale-100" : "scale-0 group-hover/bar:scale-100"}`}
          style={{ left: `${percent(currentTime)}%` }}
        />
      </div>
    </div>
  );
}

function VolumeSlider({
  volume,
  onChange,
}: {
  volume: number;
  onChange: (volume: number) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const valueAt = (clientX: number) => {
    const rect = track.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return volume;
    return clamp((clientX - rect.left) / rect.width, 0, 1);
  };
  return (
    <div
      ref={track}
      role="slider"
      aria-label="Volume"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(volume * 100)}
      className="relative h-12 w-0 cursor-pointer touch-none overflow-hidden transition-[width] group-hover/volume:mr-2 group-hover/volume:w-14 group-focus-within/volume:mr-2 group-focus-within/volume:w-14"
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture?.(event.pointerId);
        onChange(valueAt(event.clientX));
      }}
      onPointerMove={(event) => {
        if (event.buttons & 1) onChange(valueAt(event.clientX));
      }}
    >
      <div className="absolute top-1/2 right-1.5 left-1.5 h-[3px] -translate-y-1/2 bg-white/30">
        <div className="h-full bg-white" style={{ width: `${volume * 100}%` }} />
        <div
          className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white"
          style={{ left: `${volume * 100}%` }}
        />
      </div>
    </div>
  );
}

function MenuRow({
  label,
  value,
  onClick,
  checked,
}: {
  label: string;
  value?: string;
  onClick: () => void;
  checked?: boolean;
}) {
  return (
    <button
      type="button"
      role={checked === undefined ? "menuitem" : "menuitemradio"}
      aria-checked={checked}
      onClick={onClick}
      className="flex h-10 w-full items-center gap-3 px-4 text-left text-sm hover:bg-white/10"
    >
      {checked !== undefined && (
        <span className="size-5 shrink-0">{checked && <CheckGlyph />}</span>
      )}
      <span className="flex-1">{label}</span>
      {value !== undefined && (
        <>
          <span className="text-white/80">{value}</span>
          <span className="size-5 shrink-0">
            <ChevronGlyph />
          </span>
        </>
      )}
    </button>
  );
}

function SettingsMenu({
  menu,
  setMenu,
  rate,
  onRate,
  quality,
}: {
  menu: Exclude<Menu, null>;
  setMenu: (menu: Menu) => void;
  rate: number;
  onRate: (rate: number) => void;
  quality: Quality | null;
}) {
  const back = (title: string) => (
    <button
      type="button"
      onClick={() => setMenu("main")}
      className="flex h-11 w-full items-center gap-2 border-b border-white/20 px-2 text-sm font-medium hover:bg-white/10"
    >
      <span className="size-6">
        <ChevronGlyph back />
      </span>
      {title}
    </button>
  );
  return (
    <div
      role="menu"
      aria-label="Settings"
      data-player-menu
      className="absolute right-3 bottom-16 z-20 max-h-[calc(100%-5rem)] w-64 overflow-y-auto rounded-xl bg-[rgba(28,28,28,0.9)] py-2 text-white shadow-lg"
    >
      {menu === "main" && (
        <>
          <MenuRow
            label="Playback speed"
            value={speedLabel(rate)}
            onClick={() => setMenu("speed")}
          />
          <MenuRow
            label="Quality"
            value={qualityLabel(quality)}
            onClick={() => setMenu("quality")}
          />
        </>
      )}
      {menu === "speed" && (
        <>
          {back("Playback speed")}
          {SPEEDS.map((speed) => (
            <MenuRow
              key={speed}
              label={speedLabel(speed)}
              checked={speed === rate}
              onClick={() => {
                onRate(speed);
                setMenu(null);
              }}
            />
          ))}
        </>
      )}
      {menu === "quality" && (
        <>
          {back("Quality")}
          {(quality?.heights ?? [])
            .map((height, index) => ({ height, index }))
            .sort((a, b) => b.height - a.height)
            .map(({ height, index }) => (
              <MenuRow
                key={index}
                label={`${height}p`}
                checked={quality?.selected === index}
                onClick={() => {
                  quality?.select(index);
                  setMenu(null);
                }}
              />
            ))}
          <MenuRow
            label={quality?.playing ? `Auto (${quality.playing}p)` : "Auto"}
            checked={!quality || quality.selected < 0}
            onClick={() => {
              quality?.select(-1);
              setMenu(null);
            }}
          />
        </>
      )}
    </div>
  );
}

function readSavedVolume(): { volume: number; muted: boolean } | null {
  try {
    const saved = JSON.parse(localStorage.getItem(VOLUME_KEY) ?? "null") as unknown;
    if (
      saved &&
      typeof saved === "object" &&
      typeof (saved as { volume: unknown }).volume === "number" &&
      typeof (saved as { muted: unknown }).muted === "boolean"
    ) {
      const { volume, muted } = saved as { volume: number; muted: boolean };
      return { volume: clamp(volume, 0, 1), muted };
    }
  } catch {
    // Storage blocked or garbled: the defaults will do.
  }
  return null;
}

/** YouTube's player controls, over a video element. */
export function PlayerControls({
  video,
  container,
  state,
  quality,
  theater,
  onTheater,
  onNext,
}: Props) {
  const [active, setActive] = useState(true);
  const [menu, setMenu] = useState<Menu>(null);
  const [scrubbing, setScrubbing] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [flash, setFlash] = useState<Flash | null>(null);
  const hideTimer = useRef<number | undefined>(undefined);
  const flashId = useRef(0);
  const { paused, ended, waiting, currentTime, duration, volume, muted, playbackRate } = state;

  const visible = active || paused || menu !== null || scrubbing;

  const poke = useCallback(() => {
    setActive(true);
    window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => setActive(false), HIDE_AFTER_MS);
  }, []);

  const show = useCallback((content: ReactNode, side?: Flash["side"]) => {
    flashId.current += 1;
    setFlash({ id: flashId.current, content, side });
  }, []);

  const toggleFullscreen = useCallback(() => {
    const element = container.current;
    if (!element) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen?.().catch(() => {});
    } else if (element.requestFullscreen) {
      void element.requestFullscreen().catch(() => {});
    } else {
      // iOS Safari: only the video element itself can go fullscreen.
      (video.current as { webkitEnterFullscreen?: () => void } | null)?.webkitEnterFullscreen?.();
    }
  }, [container, video]);

  const run = useCallback(
    (action: PlayerAction) => {
      const element = video.current;
      if (!element) return;
      const length = Number.isFinite(element.duration) ? element.duration : 0;
      switch (action.kind) {
        case "toggle":
          if (element.paused || element.ended) {
            void element.play()?.catch(() => {});
            show(<PlayGlyph />);
          } else {
            element.pause();
            show(<PauseGlyph />);
          }
          break;
        case "seekBy":
          element.currentTime = clamp(element.currentTime + action.seconds, 0, length);
          show(
            <span className="flex flex-col items-center gap-1 text-sm font-medium">
              <span className="size-8">
                {action.seconds < 0 ? <RewindGlyph /> : <ForwardGlyph />}
              </span>
              {Math.abs(action.seconds)} seconds
            </span>,
            action.seconds < 0 ? "left" : "right",
          );
          break;
        case "seekToFraction":
          element.currentTime = length * action.fraction;
          break;
        case "seekToEnd":
          element.currentTime = length;
          break;
        case "frame":
          if (element.paused) {
            element.currentTime = clamp(element.currentTime + action.direction / 30, 0, length);
          }
          break;
        case "volumeBy":
          element.muted = false;
          element.volume = clamp(Math.round((element.volume + action.delta) * 100) / 100, 0, 1);
          show(<span className="text-lg font-medium">{Math.round(element.volume * 100)}%</span>);
          break;
        case "mute":
          element.muted = !element.muted;
          show(element.muted ? <VolumeOffGlyph /> : <VolumeHighGlyph />);
          break;
        case "fullscreen":
          toggleFullscreen();
          break;
        case "theater":
          onTheater?.();
          break;
        case "speed":
          element.playbackRate = nextSpeed(element.playbackRate, action.direction);
          show(<span className="text-lg font-medium">{element.playbackRate}x</span>);
          break;
        case "next":
          onNext?.();
          break;
      }
      poke();
    },
    [video, show, toggleFullscreen, onTheater, onNext, poke],
  );

  // The volume people chose last time, as YouTube remembers it.
  useEffect(() => {
    const element = video.current;
    const saved = readSavedVolume();
    if (element && saved) {
      element.volume = saved.volume;
      element.muted = saved.muted;
    }
  }, [video]);

  useEffect(() => {
    try {
      localStorage.setItem(VOLUME_KEY, JSON.stringify({ volume, muted }));
    } catch {
      // Not remembered, then.
    }
  }, [volume, muted]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || !isForPlayer(event.target, event.key)) return;
      const action = actionFor(event);
      if (!action) return;
      if (action.kind === "theater" && !onTheater) return;
      if (action.kind === "next" && !onNext) return;
      event.preventDefault();
      run(action);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [run, onTheater, onNext]);

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === container.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, [container]);

  // Pointer activity anywhere over the player brings the controls back.
  useEffect(() => {
    const element = container.current;
    if (!element) return undefined;
    const listeners = new AbortController();
    element.addEventListener("pointermove", poke, { signal: listeners.signal });
    element.addEventListener("pointerdown", poke, { signal: listeners.signal });
    element.addEventListener(
      "pointerleave",
      () => {
        window.clearTimeout(hideTimer.current);
        setActive(false);
      },
      { signal: listeners.signal },
    );
    poke();
    return () => {
      listeners.abort();
      window.clearTimeout(hideTimer.current);
    };
  }, [container, poke]);

  // A click anywhere else closes the settings menu.
  useEffect(() => {
    if (!menu) return undefined;
    const onDown = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (!target?.closest("[data-player-menu], [data-player-settings]")) setMenu(null);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenu(null);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  const VolumeIcon =
    muted || volume === 0 ? VolumeOffGlyph : volume < 0.5 ? VolumeLowGlyph : VolumeHighGlyph;
  const shownVolume = muted ? 0 : volume;

  return (
    <div className={`absolute inset-0 ${visible ? "" : "cursor-none"}`}>
      {/* The picture itself: a click plays or pauses, a double click goes fullscreen. */}
      <div
        className="absolute inset-0"
        onClick={() => {
          if (menu) setMenu(null);
          else run({ kind: "toggle" });
        }}
        onDoubleClick={toggleFullscreen}
      />

      {waiting && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <div
            role="status"
            aria-label="Loading"
            className="size-16 animate-spin rounded-full border-4 border-white/30 border-t-white"
          />
        </div>
      )}

      {paused && !ended && currentTime === 0 && !waiting && (
        <button
          type="button"
          aria-label="Play"
          onClick={() => run({ kind: "toggle" })}
          className="absolute top-1/2 left-1/2 grid h-12 w-17 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-2xl bg-black/70 p-3 text-white hover:bg-[#f00]"
        >
          <PlayGlyph />
        </button>
      )}

      {flash && (
        <div
          key={flash.id}
          aria-hidden
          className={`pointer-events-none absolute top-1/2 grid size-20 -translate-y-1/2 animate-player-flash place-items-center rounded-full bg-black/60 p-5 text-white ${
            flash.side === "left"
              ? "left-[15%]"
              : flash.side === "right"
                ? "right-[15%]"
                : "left-1/2 -translate-x-1/2"
          }`}
          onAnimationEnd={() => setFlash((current) => (current?.id === flash.id ? null : current))}
        >
          {flash.content}
        </div>
      )}

      {menu && (
        <SettingsMenu
          menu={menu}
          setMenu={setMenu}
          rate={playbackRate}
          onRate={(rate) => {
            if (video.current) video.current.playbackRate = rate;
          }}
          quality={quality}
        />
      )}

      <div
        data-player-controls
        className={`absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 via-black/30 to-transparent pt-12 transition-opacity duration-200 ${
          visible ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
        <ProgressBar
          state={state}
          onSeek={(time) => {
            if (video.current) video.current.currentTime = time;
          }}
          onScrub={setScrubbing}
        />
        <div className="flex h-12 items-center px-1.5 text-white">
          <ControlButton
            label={ended ? "Replay" : paused ? "Play (k)" : "Pause (k)"}
            onClick={() => run({ kind: "toggle" })}
          >
            {ended ? <ReplayGlyph /> : paused ? <PlayGlyph /> : <PauseGlyph />}
          </ControlButton>
          {onNext && (
            <ControlButton label="Next (SHIFT+n)" onClick={onNext}>
              <NextGlyph />
            </ControlButton>
          )}
          <div className="group/volume flex items-center">
            <ControlButton
              label={muted ? "Unmute (m)" : "Mute (m)"}
              onClick={() => run({ kind: "mute" })}
            >
              <VolumeIcon />
            </ControlButton>
            <VolumeSlider
              volume={shownVolume}
              onChange={(value) => {
                const element = video.current;
                if (!element) return;
                element.volume = value;
                element.muted = value === 0;
              }}
            />
          </div>
          <span className="px-1 text-[13px] whitespace-nowrap tabular-nums">
            {formatDuration(currentTime)} / {formatDuration(duration)}
          </span>
          <span className="flex-1" />
          <span data-player-settings>
            <ControlButton
              label="Settings"
              pressed={menu !== null}
              onClick={() => setMenu((current) => (current ? null : "main"))}
            >
              <span className={`size-full transition-transform ${menu ? "rotate-30" : ""}`}>
                <SettingsGlyph />
              </span>
            </ControlButton>
          </span>
          {onTheater && !fullscreen && (
            <ControlButton
              label={theater ? "Default view (t)" : "Theater mode (t)"}
              onClick={onTheater}
              pressed={theater}
            >
              {theater ? <DefaultViewGlyph /> : <TheaterGlyph />}
            </ControlButton>
          )}
          <ControlButton
            label={fullscreen ? "Exit full screen (f)" : "Full screen (f)"}
            onClick={toggleFullscreen}
          >
            {fullscreen ? <ExitFullscreenGlyph /> : <FullscreenGlyph />}
          </ControlButton>
        </div>
      </div>
    </div>
  );
}
