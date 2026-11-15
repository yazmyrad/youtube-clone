import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { listAccounts } from "../api/account";
import { authApi } from "../api/client";
import { ACCOUNTS_KEY, useAuth, type Me } from "../hooks/useAuth";
import { Avatar } from "./Avatar";
import { channelPath } from "./format";

const item = "flex h-10 w-full items-center gap-3 px-4 text-left text-sm hover:bg-hover";

const BACK = "M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z";
const FORWARD = "M8.59 16.59 10 18l6-6-6-6-1.41 1.41L13.17 12z";

const Chevron = ({ back = false }: { back?: boolean }) => (
  <svg viewBox="0 0 24 24" className="size-5" fill="currentColor" aria-hidden>
    <path d={back ? BACK : FORWARD} />
  </svg>
);

/** YouTube's "Switch account": the accounts signed in in this browser, and adding one. */
function Accounts({
  user,
  onBack,
  onDone,
}: {
  user: Me;
  onBack: () => void;
  onDone: () => void;
}) {
  const { switchAccount, logoutAll } = useAuth();
  const { pathname, search } = useLocation();
  const accounts = useQuery({ queryKey: ACCOUNTS_KEY, queryFn: () => listAccounts(authApi) });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    setError(null);
    setBusy(true);
    try {
      await action();
      onDone();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const here = encodeURIComponent(pathname + search);
  return (
    <div>
      <div className="flex items-center gap-2 border-b border-line px-2 pb-2">
        <button
          type="button"
          aria-label="Back"
          onClick={onBack}
          className="grid size-10 place-items-center rounded-full hover:bg-hover"
        >
          <Chevron back />
        </button>
        <h2 className="font-medium">Accounts</h2>
      </div>
      <ul aria-label="Signed-in accounts" className="py-2">
        {accounts.isPending && <li aria-busy="true" className="h-14" />}
        {accounts.data?.map((account) => {
          const current = account.id === user.id;
          return (
            <li key={account.id}>
              <button
                type="button"
                disabled={busy}
                aria-current={current ? "true" : undefined}
                onClick={() => void run(() => switchAccount(account.id))}
                className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-hover disabled:opacity-60"
              >
                <Avatar
                  name={account.display_name}
                  username={account.username}
                  src={account.avatar_url}
                  className="size-9 text-sm"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {account.display_name}
                  </span>
                  <span className="block truncate text-xs text-ink-muted">
                    @{account.username}
                  </span>
                </span>
                {current && (
                  <svg
                    viewBox="0 0 24 24"
                    className="size-5"
                    fill="currentColor"
                    aria-label="Current"
                  >
                    <path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
                  </svg>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      <div className="border-t border-line pt-2">
        <Link to={`/login?add=1&next=${here}`} onClick={onDone} className={item}>
          Add account
        </Link>
        <button type="button" disabled={busy} onClick={() => void run(logoutAll)} className={item}>
          Sign out of all accounts
        </button>
      </div>
      {error && (
        <p role="alert" className="px-4 pt-1 text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export function UserMenu({ user, onLogout }: { user: Me; onLogout: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<"main" | "accounts">("main");
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
      setOpen(false);
    } catch {
      setFailed(true);
    }
  }

  const close = () => setOpen(false);
  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label="Account menu"
        aria-expanded={open}
        onClick={() => {
          setPanel("main");
          setOpen((value) => !value);
        }}
        className="rounded-full"
      >
        <Avatar
          name={user.display_name}
          username={user.username}
          src={user.avatar_url}
          className="size-8 text-sm"
        />
      </button>
      {open && (
        <div className="absolute top-10 right-0 w-72 rounded-xl border border-line bg-page py-2 shadow-lg">
          {panel === "accounts" ? (
            <Accounts user={user} onBack={() => setPanel("main")} onDone={close} />
          ) : (
            <>
              <div className="flex gap-3 border-b border-line px-4 pb-3">
                <Avatar
                  name={user.display_name}
                  username={user.username}
                  src={user.avatar_url}
                  className="size-10"
                />
                <div className="min-w-0">
                  <p className="truncate font-medium">{user.display_name}</p>
                  <p className="truncate text-sm text-ink-muted">@{user.username}</p>
                  <Link
                    to={channelPath(user.username)}
                    onClick={close}
                    className="mt-2 inline-block text-sm text-accent hover:underline"
                  >
                    View your channel
                  </Link>
                </div>
              </div>
              <div className="pt-2">
                <button type="button" onClick={() => setPanel("accounts")} className={item}>
                  <span className="flex-1">Switch account</span>
                  <Chevron />
                </button>
                <Link to="/customize" onClick={close} className={item}>
                  Customize channel
                </Link>
                <button type="button" onClick={() => void signOut()} className={item}>
                  Sign out
                </button>
              </div>
              {failed && (
                <p role="alert" className="px-4 pt-1 text-sm text-danger">
                  Couldn't sign out. Please try again.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
