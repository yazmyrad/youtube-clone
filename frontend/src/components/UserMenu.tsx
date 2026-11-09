import { useEffect, useRef, useState } from "react";

import type { Me } from "../hooks/useAuth";

export function UserMenu({ user, onLogout }: { user: Me; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const initial = user.display_name.charAt(0).toUpperCase();

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label="Account menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="grid size-8 place-items-center rounded-full bg-accent text-sm font-medium text-white"
      >
        {initial}
      </button>
      {open && (
        <div className="absolute top-10 right-0 w-64 rounded-xl border border-line bg-page py-2 shadow-lg">
          <div className="border-b border-line px-4 pb-3">
            <p className="truncate font-medium">{user.display_name}</p>
            <p className="truncate text-sm text-ink-muted">@{user.username}</p>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="mt-2 block h-10 w-full px-4 text-left text-sm hover:bg-hover"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
