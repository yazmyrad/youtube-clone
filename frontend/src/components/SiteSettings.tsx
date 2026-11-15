import { useCallback, useRef, useState } from "react";

import { useDismiss } from "../hooks/useDismiss";
import { AppearancePanel, AppearanceRow } from "./Appearance";
import { MoreIcon } from "./icons";

/** The signed-out visitor's ⋮ Settings menu, as on YouTube: the account menu has the same. */
export function SiteSettings() {
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<"main" | "appearance">("main");
  const root = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, root, close);

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label="Settings"
        aria-expanded={open}
        onClick={() => {
          setPanel("main");
          setOpen((value) => !value);
        }}
        className="grid size-10 place-items-center rounded-full hover:bg-hover"
      >
        <MoreIcon />
      </button>
      {open && (
        <div className="absolute top-11 right-0 z-10 w-72 rounded-xl border border-line bg-page py-2 shadow-lg">
          {panel === "appearance" ? (
            <AppearancePanel onBack={() => setPanel("main")} />
          ) : (
            <AppearanceRow onOpen={() => setPanel("appearance")} />
          )}
        </div>
      )}
    </div>
  );
}
