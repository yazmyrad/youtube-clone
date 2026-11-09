import { Link, Navigate, useSearchParams } from "react-router-dom";

import { AuthCard, AuthForm, Field } from "../components/AuthForm";
import { useAuth } from "../hooks/useAuth";
import { safeNext } from "./safeNext";

export function LoginPage() {
  const { user, login } = useAuth();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));

  // Also what moves the page on after a successful login.
  if (user) return <Navigate to={next} replace />;

  return (
    <AuthCard title="Sign in" subtitle="Use your account to continue">
      <AuthForm
        submitLabel="Sign in"
        onSubmit={(form) =>
          login({ email: String(form.get("email")), password: String(form.get("password")) })
        }
        footer={
          <Link to={`/register?next=${encodeURIComponent(next)}`} className="font-medium text-accent">
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
