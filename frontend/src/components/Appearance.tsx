import { setTheme, THEME_NAMES, THEME_OPTIONS, useTheme } from "../theme";
import { AppearanceIcon, CheckIcon, ChevronIcon } from "./icons";

export const menuItem = "flex h-10 w-full items-center gap-3 px-4 text-left text-sm hover:bg-hover";

/** A popup menu's sub-panel heading, with the way back to the main panel. */
export function PanelHeader({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <div className="flex items-center gap-2 border-b border-line px-2 pb-2">
      <button
        type="button"
        aria-label="Back"
        onClick={onBack}
        className="grid size-10 place-items-center rounded-full hover:bg-hover"
      >
        <ChevronIcon back />
      </button>
      <h2 className="font-medium">{title}</h2>
    </div>
  );
}

/** The main panel's row: "Appearance: Device theme", opening the panel below. */
export function AppearanceRow({ onOpen }: { onOpen: () => void }) {
  const theme = useTheme();
  return (
    <button type="button" onClick={onOpen} className={menuItem}>
      <AppearanceIcon />
      <span className="flex-1">Appearance: {THEME_NAMES[theme]}</span>
      <ChevronIcon />
    </button>
  );
}

/** YouTube's Appearance panel: the device's theme, dark or light. */
export function AppearancePanel({ onBack }: { onBack: () => void }) {
  const theme = useTheme();
  return (
    <div>
      <PanelHeader title="Appearance" onBack={onBack} />
      <p className="px-4 pt-3 pb-1 text-xs text-ink-muted">Setting applies to this browser only</p>
      <div role="radiogroup" aria-label="Appearance">
        {THEME_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={option.value === theme}
            onClick={() => setTheme(option.value)}
            className={menuItem}
          >
            <span className="size-5 shrink-0">{option.value === theme && <CheckIcon />}</span>
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
