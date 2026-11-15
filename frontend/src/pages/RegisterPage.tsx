import { useRef } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";

import { AuthCard, AuthForm, Field } from "../components/AuthForm";
import { useAuth } from "../hooks/useAuth";
import { safeNext } from "./safeNext";

export function RegisterPage() {
  const { user, isLoading, register } = useAuth();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const adding = params.get("add") === "1";
  // Who was signed in when the page opened: the account being added is someone else.
  const startedAs = useRef<string | null | undefined>(undefined);
  if (!isLoading && startedAs.current === undefined) startedAs.current = user?.id ?? null;

  // Also what moves the page on once the new account is signed in.
  // Also what moves the page on after a successful sign-in. Adding an account, the page
  // stays until the new one is in.
  if (isLoading) return null;
  if (user && !(adding && user.id === startedAs.current)) return <Navigate to={next} replace />;

  return (
    <AuthCard title="Create your account" subtitle="Upload, comment and subscribe">
      <AuthForm
        submitLabel="Create account"
        onSubmit={(form) =>
          register({
            username: String(form.get("username")),
            email: String(form.get("email")),
            password: String(form.get("password")),
            display_name: String(form.get("display_name")),
          })
        }
        footer={
          <Link
            to={`/login?next=${encodeURIComponent(next)}${adding ? "&add=1" : ""}`}
            className="font-medium text-accent"
          >
            Sign in instead
          </Link>
        }
      >
        <Field label="Name" name="display_name" autoComplete="name" maxLength={50} autoFocus />
        <Field
          label="Username"
          name="username"
          autoComplete="username"
          pattern="[a-zA-Z0-9_\-]{3,30}"
          title="3 to 30 letters, digits, underscores or hyphens"
          hint="3 to 30 letters, digits, underscores or hyphens"
        />
        <Field label="Email" name="email" type="email" autoComplete="email" />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={8}
          maxLength={128}
          hint="At least 8 characters"
        />
      </AuthForm>
    </AuthCard>
  );
}
