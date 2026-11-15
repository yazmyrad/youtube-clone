import { useRef } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";

import { AuthCard, AuthForm, Field } from "../components/AuthForm";
import { useAuth } from "../hooks/useAuth";
import { safeNext } from "./safeNext";

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
