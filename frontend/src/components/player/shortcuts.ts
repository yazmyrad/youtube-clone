/** YouTube's keyboard shortcuts, as plain data, so they can be tested without a video. */

export const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2] as const;

export type PlayerAction =
  | { kind: "toggle" }
  | { kind: "seekBy"; seconds: number }
  | { kind: "seekToFraction"; fraction: number }
  | { kind: "seekToEnd" }
  | { kind: "frame"; direction: -1 | 1 }
  | { kind: "volumeBy"; delta: number }
  | { kind: "mute" }
  | { kind: "fullscreen" }
  | { kind: "theater" }
  | { kind: "speed"; direction: -1 | 1 }
  | { kind: "next" };

interface KeyLike {
  key: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

export function actionFor(event: KeyLike): PlayerAction | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  const key = event.key;
  if (/^[0-9]$/.test(key)) return { kind: "seekToFraction", fraction: Number(key) / 10 };
  switch (key) {
    case " ":
    case "k":
    case "K":
      return { kind: "toggle" };
    case "j":
    case "J":
      return { kind: "seekBy", seconds: -10 };
    case "l":
    case "L":
      return { kind: "seekBy", seconds: 10 };
    case "ArrowLeft":
      return { kind: "seekBy", seconds: -5 };
    case "ArrowRight":
      return { kind: "seekBy", seconds: 5 };
    case "ArrowUp":
      return { kind: "volumeBy", delta: 0.05 };
    case "ArrowDown":
      return { kind: "volumeBy", delta: -0.05 };
    case "Home":
      return { kind: "seekToFraction", fraction: 0 };
    case "End":
      return { kind: "seekToEnd" };
    case "m":
    case "M":
      return { kind: "mute" };
    case "f":
    case "F":
      return { kind: "fullscreen" };
    case "t":
    case "T":
      return { kind: "theater" };
    case ",":
      return { kind: "frame", direction: -1 };
    case ".":
      return { kind: "frame", direction: 1 };
    case "<":
      return { kind: "speed", direction: -1 };
    case ">":
      return { kind: "speed", direction: 1 };
    case "N":
      return event.shiftKey ? { kind: "next" } : null;
    default:
      return null;
  }
}

/** Keys typed into a field, or pressed on a focused button or link, aren't the player's. */
export function isForPlayer(target: EventTarget | null, key: string): boolean {
  if (!(target instanceof HTMLElement)) return true;
  if (target.closest("[aria-modal='true'], dialog, [role='dialog'], [role='menu']")) return false;
  if (target.isContentEditable || target.closest("input, textarea, select")) return false;
  // Space or Enter on a focused button or link presses it, as it would anywhere.
  if ((key === " " || key === "Enter") && target.closest("button, a, [role='button']")) {
    return false;
  }
  return true;
}

export function nextSpeed(current: number, direction: -1 | 1): number {
  const index = SPEEDS.findIndex((speed) => speed >= current - 1e-9);
  const at = index === -1 ? SPEEDS.length - 1 : index;
  return SPEEDS[Math.min(SPEEDS.length - 1, Math.max(0, at + direction))]!;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
