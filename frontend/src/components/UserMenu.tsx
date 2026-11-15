import { useQuery } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { listAccounts } from "../api/account";
import { authApi } from "../api/client";
import { ACCOUNTS_KEY, useAuth, type Me } from "../hooks/useAuth";
import { useDismiss } from "../hooks/useDismiss";
import { AppearancePanel, AppearanceRow, menuItem as item, PanelHeader } from "./Appearance";
import { Avatar } from "./Avatar";
import { channelPath } from "./format";
import { CheckIcon, ChevronIcon as Chevron } from "./icons";

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
      <PanelHeader title="Accounts" onBack={onBack} />
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
                  <span role="img" aria-label="Current">
                    <CheckIcon />
                  </span>
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
  const [panel, setPanel] = useState<"main" | "accounts" | "appearance">("main");
  const [failed, setFailed] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, root, close);

  async function signOut() {
    setFailed(false);
    try {
      await onLogout();
      setOpen(false);
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
          {panel === "accounts" && (
            <Accounts user={user} onBack={() => setPanel("main")} onDone={close} />
          )}
          {panel === "appearance" && <AppearancePanel onBack={() => setPanel("main")} />}
          {panel === "main" && (
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
              <div className="mt-2 border-t border-line pt-2">
                <AppearanceRow onOpen={() => setPanel("appearance")} />
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
