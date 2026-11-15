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
  /** The Ambient mode switch, offered in the dark theme only, as on YouTube. */
  ambient?: { on: boolean; onToggle: () => void };
}

/** Keys that scroll the page: the player takes them only when it has focus. */
const PAGE_KEYS = new Set([" ", "ArrowUp", "ArrowDown", "Home", "End"]);
const TOGGLES = new Set<PlayerAction["kind"]>(["toggle", "mute", "fullscreen", "theater", "next"]);

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
  shortcut,
  onClick,
  children,
  pressed,
}: {
  label: string;
  /** YouTube's tooltip shows it, as in "Play (k)". */
  shortcut?: string;
  onClick: () => void;
  children: ReactNode;
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-keyshortcuts={shortcut}
      title={shortcut ? `${label} (${shortcut.toLowerCase()})` : label}
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
  // While dragging: where the thumb is. The video seeks once, on release, rather than on every
  // move, which would make hls.js drop and refetch its buffer dozens of times a second.
  const [scrub, setScrub] = useState<number | null>(null);
  const { duration, currentTime, bufferedEnd } = state;
  const shown = scrub ?? currentTime;
  const percent = (time: number) => (duration > 0 ? clamp(time / duration, 0, 1) * 100 : 0);

  const timeAt = (clientX: number) => {
    const rect = bar.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || duration <= 0) return 0;
    return clamp((clientX - rect.left) / rect.width, 0, 1) * duration;
  };
  const end = (seek: boolean) => {
    if (scrub === null) return;
    if (seek) onSeek(scrub);
    setScrub(null);
    onScrub(false);
  };

  return (
    <div
      ref={bar}
      role="slider"
      tabIndex={0}
      aria-label="Seek"
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={Math.round(shown)}
      aria-valuetext={`${formatDuration(shown)} of ${formatDuration(duration)}`}
      className="group/bar relative mx-3 flex h-4 cursor-pointer touch-none items-end outline-none focus-visible:ring-2 focus-visible:ring-white"
      onPointerMove={(event) => {
        const time = timeAt(event.clientX);
        if (event.pointerType !== "touch") setHover(time);
        if (scrub !== null) setScrub(time);
      }}
      onPointerLeave={() => setHover(null)}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.currentTarget.setPointerCapture?.(event.pointerId);
        setScrub(timeAt(event.clientX));
        onScrub(true);
      }}
      onPointerUp={() => end(true)}
      onPointerCancel={() => end(false)}
      onLostPointerCapture={() => end(true)}
      onKeyDown={(event) => {
        const step = event.key === "ArrowLeft" ? -5 : event.key === "ArrowRight" ? 5 : 0;
        if (!step) return;
        event.preventDefault();
        onSeek(clamp(currentTime + step, 0, duration));
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
        className={`relative w-full bg-white/20 transition-[height] ${scrub !== null ? "h-[5px]" : "h-[3px] group-hover/bar:h-[5px]"}`}
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
          style={{ width: `${percent(shown)}%` }}
        />
        <div
          className={`absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#f00] transition-transform ${scrub !== null ? "scale-100" : "scale-0 group-hover/bar:scale-100 group-focus-visible/bar:scale-100"}`}
          style={{ left: `${percent(shown)}%` }}
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
      tabIndex={0}
      aria-label="Volume"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(volume * 100)}
      className="relative h-12 w-0 cursor-pointer touch-none overflow-hidden outline-none transition-[width] group-focus-within/volume:mr-2 group-focus-within/volume:w-14 group-hover/volume:mr-2 group-hover/volume:w-14 focus-visible:ring-2 focus-visible:ring-white"
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.currentTarget.setPointerCapture?.(event.pointerId);
        onChange(valueAt(event.clientX));
      }}
      onPointerMove={(event) => {
        if (event.buttons & 1) onChange(valueAt(event.clientX));
      }}
      onKeyDown={(event) => {
        const step =
          event.key === "ArrowLeft" || event.key === "ArrowDown"
            ? -0.05
            : event.key === "ArrowRight" || event.key === "ArrowUp"
              ? 0.05
              : 0;
        if (!step) return;
        event.preventDefault();
        onChange(clamp(Math.round((volume + step) * 100) / 100, 0, 1));
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
      className="flex h-10 w-full items-center gap-3 px-4 text-left text-sm outline-none hover:bg-white/10 focus-visible:bg-white/20"
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

/** A setting that is on or off, with YouTube's little switch. */
function SwitchRow({ label, on, onToggle }: { label: string; on: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="menuitemcheckbox"
      aria-checked={on}
      onClick={onToggle}
      className="flex h-10 w-full items-center gap-3 px-4 text-left text-sm outline-none hover:bg-white/10 focus-visible:bg-white/20"
    >
      <span className="flex-1">{label}</span>
      <span
        aria-hidden
        className={`relative h-3.5 w-9 rounded-full transition-colors ${on ? "bg-white/50" : "bg-white/30"}`}
      >
        <span
          className={`absolute top-1/2 size-5 -translate-y-1/2 rounded-full shadow transition-all ${
            on ? "left-4 bg-white" : "left-0 bg-[#bbbbbb]"
          }`}
        />
      </span>
    </button>
  );
}

function SettingsMenu({
  menu,
  setMenu,
  rate,
  onRate,
  quality,
  ambient,
}: {
  menu: Exclude<Menu, null>;
  setMenu: (menu: Menu) => void;
  rate: number;
  onRate: (rate: number) => void;
  quality: Quality | null;
  ambient?: Props["ambient"];
}) {
  const box = useRef<HTMLDivElement>(null);
  // Focus follows the menu, so it works from the keyboard as well as the mouse.
  useEffect(() => {
    box.current?.querySelector<HTMLElement>("[role^=menuitem]")?.focus();
  }, [menu]);
  const back = (title: string) => (
    <button
      type="button"
      role="menuitem"
      onClick={() => setMenu("main")}
      className="flex h-11 w-full items-center gap-2 border-b border-white/20 px-2 text-sm font-medium outline-none hover:bg-white/10 focus-visible:bg-white/20"
    >
      <span className="size-6">
        <ChevronGlyph back />
      </span>
      {title}
    </button>
  );
  return (
    <div
      ref={box}
      role="menu"
      aria-label="Settings"
      data-player-menu
      onKeyDown={(event) => {
        const step = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
        if (!step) return;
        event.preventDefault();
        const items = [...(box.current?.querySelectorAll<HTMLElement>("[role^=menuitem]") ?? [])];
        const at = items.indexOf(document.activeElement as HTMLElement);
        items[(at + step + items.length) % items.length]?.focus();
      }}
      className="absolute right-3 bottom-16 z-20 max-h-[calc(100%-5rem)] w-64 overflow-y-auto rounded-xl bg-[rgba(28,28,28,0.9)] py-2 text-white shadow-lg"
    >
      {menu === "main" && (
        <>
          {ambient && (
            <SwitchRow label="Ambient mode" on={ambient.on} onToggle={ambient.onToggle} />
          )}
          <MenuRow
            label="Playback speed"
            value={speedLabel(rate)}
            onClick={() => setMenu("speed")}
          />
          {/* Safari's own HLS playback picks the quality itself: nothing to choose. */}
          {quality && (
            <MenuRow
              label="Quality"
              value={qualityLabel(quality)}
              onClick={() => setMenu("quality")}
            />
          )}
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
  ambient,
}: Props) {
  const [active, setActive] = useState(true);
  const [menu, setMenu] = useState<Menu>(null);
  const [scrubbing, setScrubbing] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [flash, setFlash] = useState<Flash | null>(null);
  // The pointer resting on the controls, or focus inside the player, keeps them up.
  const [overControls, setOverControls] = useState(false);
  const [focused, setFocused] = useState(false);
  const hideTimer = useRef<number | undefined>(undefined);
  const flashTimer = useRef<number | undefined>(undefined);
  const flashId = useRef(0);
  const restored = useRef(false);
  const { paused, ended, waiting, currentTime, duration, volume, muted, playbackRate } = state;

  const visible = active || paused || menu !== null || scrubbing || overControls || focused;

  const poke = useCallback(() => {
    setActive(true);
    window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => setActive(false), HIDE_AFTER_MS);
  }, []);

  const show = useCallback((content: ReactNode, side?: Flash["side"]) => {
    flashId.current += 1;
    const id = flashId.current;
    setFlash({ id, content, side });
    // A timer, not animationend: with reduced motion there is no animation to end.
    window.clearTimeout(flashTimer.current);
    flashTimer.current = window.setTimeout(
      () => setFlash((current) => (current?.id === id ? null : current)),
      600,
    );
  }, []);

  const toggleFullscreen = useCallback(() => {
    const element = container.current;
    if (!element) return;
    const webkit = document as Document & {
      webkitFullscreenElement?: Element | null;
      webkitExitFullscreen?: () => void;
    };
    const target = element as HTMLElement & { webkitRequestFullscreen?: () => void };
    if (document.fullscreenElement) {
      void document.exitFullscreen?.().catch(() => {});
    } else if (webkit.webkitFullscreenElement) {
      webkit.webkitExitFullscreen?.();
    } else if (element.requestFullscreen) {
      void element.requestFullscreen().catch(() => {});
    } else if (target.webkitRequestFullscreen) {
      target.webkitRequestFullscreen();
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
          // Unmuting at zero would stay silent.
          if (!element.muted && element.volume === 0) element.volume = 0.5;
          show(element.muted ? <VolumeOffGlyph /> : <VolumeHighGlyph />);
          break;
        case "fullscreen":
          toggleFullscreen();
          break;
        case "theater":
          if (!document.fullscreenElement) onTheater?.();
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
    restored.current = true;
  }, [video]);

  useEffect(() => {
    // Not before the saved value was read back, or the defaults would overwrite it.
    if (!restored.current) return;
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
      // Keys that scroll the page do so, unless the player has focus, as on YouTube.
      const inPlayer = container.current?.contains(document.activeElement) ?? false;
      if (PAGE_KEYS.has(event.key) && !inPlayer) return;
      // Holding a key repeats seeks and volume steps, not toggles.
      if (event.repeat && TOGGLES.has(action.kind)) return;
      event.preventDefault();
      run(action);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [run, onTheater, onNext, container]);

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
      (event) => {
        // A tap ends with a leave; the controls stay for their usual three seconds.
        if (event.pointerType === "touch") return;
        window.clearTimeout(hideTimer.current);
        setActive(false);
      },
      { signal: listeners.signal },
    );
    element.addEventListener("focusin", () => setFocused(true), { signal: listeners.signal });
    element.addEventListener(
      "focusout",
      (event) => {
        if (!element.contains(event.relatedTarget as Node | null)) setFocused(false);
      },
      { signal: listeners.signal },
    );
    poke();
    return () => {
      listeners.abort();
      window.clearTimeout(hideTimer.current);
      window.clearTimeout(flashTimer.current);
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
          // Focus, so the page-scrolling keys (space, arrows) belong to the player now.
          container.current?.focus({ preventScroll: true });
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
            className="size-16 animate-spin rounded-full border-4 border-white/30 border-t-white motion-reduce:animate-none"
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
          className={`pointer-events-none absolute top-1/2 grid size-20 -translate-y-1/2 animate-player-flash motion-reduce:animate-none place-items-center rounded-full bg-black/60 p-5 text-white ${
            flash.side === "left"
              ? "left-[15%]"
              : flash.side === "right"
                ? "right-[15%]"
                : "left-1/2 -translate-x-1/2"
          }`}
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
          ambient={ambient}
        />
      )}

      <div
        data-player-controls
        onPointerEnter={(event) => {
          if (event.pointerType !== "touch") setOverControls(true);
        }}
        onPointerLeave={() => setOverControls(false)}
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
            label={ended ? "Replay" : paused ? "Play" : "Pause"}
            shortcut="K"
            onClick={() => run({ kind: "toggle" })}
          >
            {ended ? <ReplayGlyph /> : paused ? <PlayGlyph /> : <PauseGlyph />}
          </ControlButton>
          {onNext && (
            <ControlButton label="Next" shortcut="Shift+N" onClick={onNext}>
              <NextGlyph />
            </ControlButton>
          )}
          <div className="group/volume flex items-center">
            <ControlButton
              label={muted ? "Unmute" : "Mute"}
              shortcut="M"
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
              <span
                className={`size-full transition-transform motion-reduce:transition-none ${menu ? "rotate-30" : ""}`}
              >
                <SettingsGlyph />
              </span>
            </ControlButton>
          </span>
          {onTheater && !fullscreen && (
            <ControlButton label="Theater mode" shortcut="T" onClick={onTheater} pressed={theater}>
              {theater ? <DefaultViewGlyph /> : <TheaterGlyph />}
            </ControlButton>
          )}
          <ControlButton
            label={fullscreen ? "Exit full screen" : "Full screen"}
            shortcut="F"
            onClick={toggleFullscreen}
          >
            {fullscreen ? <ExitFullscreenGlyph /> : <FullscreenGlyph />}
          </ControlButton>
        </div>
      </div>
    </div>
  );
}
