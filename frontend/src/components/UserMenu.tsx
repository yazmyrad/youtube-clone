import { useEffect, useRef, useState } from "react";

import type { Me } from "../hooks/useAuth";
import { Avatar } from "./Avatar";

export function UserMenu({ user, onLogout }: { user: Me; onLogout: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
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

  async function signOut() {
    setFailed(false);
    try {
      await onLogout();
    } catch {
      setFailed(true);
    }
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label="Account menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="rounded-full"
      >
        <Avatar name={user.display_name} username={user.username} className="size-8 text-sm" />
      </button>
      {open && (
        <div className="absolute top-10 right-0 w-64 rounded-xl border border-line bg-page py-2 shadow-lg">
          <div className="border-b border-line px-4 pb-3">
            <p className="truncate font-medium">{user.display_name}</p>
            <p className="truncate text-sm text-ink-muted">@{user.username}</p>
          </div>
          <button
            type="button"
            onClick={() => void signOut()}
            className="mt-2 block h-10 w-full px-4 text-left text-sm hover:bg-hover"
          >
            Sign out
          </button>
          {failed && (
            <p role="alert" className="px-4 pt-1 text-sm text-danger">
              Couldn't sign out. Please try again.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
