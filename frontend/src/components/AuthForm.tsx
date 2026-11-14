import { useState, type FormEvent, type InputHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { failureMessage } from "../api/errors";
import { Logo } from "./icons";

export function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <main className="grid min-h-screen place-items-center bg-hover p-4">
      <div className="w-full max-w-md rounded-3xl bg-page p-8 sm:p-10">
        <Link to="/" aria-label="Home" className="inline-block">
          <Logo />
        </Link>
        <h1 className="mt-6 text-3xl">{title}</h1>
        <p className="mt-2 text-sm text-ink-muted">{subtitle}</p>
        {children}
      </div>
    </main>
  );
}

export function Field({
  label,
  hint,
  ...input
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className="block text-sm font-medium">
      {label}
      <input
        required
        {...input}
        className="mt-1 block h-12 w-full rounded-lg border border-line px-3 text-base font-normal outline-none focus:border-accent focus:ring-1 focus:ring-accent"
      />
      {hint && <span className="mt-1 block text-xs font-normal text-ink-muted">{hint}</span>}
    </label>
  );
}

export function AuthForm({
  submitLabel,
  onSubmit,
  footer,
  children,
}: {
  submitLabel: string;
  onSubmit: (form: FormData) => Promise<void>;
  footer: ReactNode;
  children: ReactNode;
}) {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await onSubmit(new FormData(event.currentTarget));
    } catch (failure) {
      setError(failureMessage(failure));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} className="mt-6 space-y-4">
      {children}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex items-center justify-between gap-4 pt-2">
        <span className="text-sm">{footer}</span>
        <button
          type="submit"
          disabled={pending}
          className="h-10 shrink-0 rounded-full bg-accent px-6 text-sm font-medium text-on-accent hover:opacity-90 disabled:opacity-50"
        >
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
