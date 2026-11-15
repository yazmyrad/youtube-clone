import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";

import { listAccounts } from "../api/account";
import { authApi } from "../api/client";
import { AuthCard, AuthForm, Field } from "../components/AuthForm";
import { Avatar } from "../components/Avatar";
import { ACCOUNTS_KEY, useAuth } from "../hooks/useAuth";
import { safeNext } from "./safeNext";

/** YouTube's "Choose an account": the accounts still signed in in this browser, one click
 * away, after the one in use was signed out. Never picked on the visitor's behalf. */
function ChooseAccount() {
  const { switchAccount } = useAuth();
  const accounts = useQuery({ queryKey: ACCOUNTS_KEY, queryFn: () => listAccounts(authApi) });
  const [error, setError] = useState<string | null>(null);
  const items = accounts.data ?? [];
  if (items.length === 0) return null;
  return (
    <section aria-labelledby="choose-title" className="mb-6 border-b border-line pb-4">
      <h2 id="choose-title" className="mb-2 text-sm font-medium">
        Choose an account
      </h2>
      <ul>
        {items.map((account) => (
          <li key={account.id}>
            <button
              type="button"
              onClick={() => {
                setError(null);
                switchAccount(account.id).catch((failure: Error) => setError(failure.message));
              }}
              className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-hover"
            >
              <Avatar
                name={account.display_name}
                username={account.username}
                src={account.avatar_url}
                className="size-9 text-sm"
              />
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{account.display_name}</span>
                <span className="block truncate text-xs text-ink-muted">@{account.username}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {error && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
      <p className="mt-3 text-sm text-ink-muted">Or use another account:</p>
    </section>
  );
}

export function LoginPage() {
  const { user, isLoading, login } = useAuth();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const adding = params.get("add") === "1";
  // Who was signed in when the page opened: the account being added is someone else.
  const startedAs = useRef<string | null | undefined>(undefined);
  if (!isLoading && startedAs.current === undefined) startedAs.current = user?.id ?? null;

  // Also what moves the page on after a successful sign-in. Adding an account, the page
  // stays until the new one is in.
  if (isLoading) return null;
  if (user && !(adding && user.id === startedAs.current)) return <Navigate to={next} replace />;

  return (
    <AuthCard
      title={adding ? "Add account" : "Sign in"}
      subtitle={adding ? "Sign in to another account" : "Use your account to continue"}
    >
      {!user && <ChooseAccount />}
      <AuthForm
        submitLabel="Sign in"
        onSubmit={(form) =>
          login({ email: String(form.get("email")), password: String(form.get("password")) })
        }
        footer={
          <Link
            to={`/register?next=${encodeURIComponent(next)}${adding ? "&add=1" : ""}`}
            className="font-medium text-accent"
          >
            Create account
          </Link>
        }
      >
        <Field label="Email" name="email" type="email" autoComplete="email" autoFocus />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          maxLength={128}
        />
      </AuthForm>
    </AuthCard>
  );
}
