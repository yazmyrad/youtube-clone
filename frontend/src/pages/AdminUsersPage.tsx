import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { LoadMore } from "../components/LoadMore";
import { channelPath } from "../components/format";
import { useAdminUsers, useChangeUser, type AdminUser } from "../hooks/useAdminUsers";
import { useAuth } from "../hooks/useAuth";
import { NotFoundPage } from "./NotFoundPage";

const ROLES: AdminUser["role"][] = ["user", "moderator", "admin"];

function Row({ user, self }: { user: AdminUser; self: boolean }) {
  const change = useChangeUser();
  // An admin can't demote or disable themselves, so at least one admin remains.
  const locked = self || change.isPending;
  return (
    <tr className="border-t border-line align-top">
      <td className="py-3 pr-3">
        <Link to={channelPath(user.username)} className="font-medium hover:underline">
          {user.display_name}
        </Link>
        <p className="text-xs text-ink-muted">
          @{user.username} · {user.email}
        </p>
        {change.isError && (
          <p role="alert" className="mt-1 text-xs text-danger">
            {change.error.message}
          </p>
        )}
      </td>
      <td className="py-3 pr-3">
        <select
          aria-label={`Role of ${user.username}`}
          value={user.role}
          disabled={locked}
          onChange={(event) =>
            change.mutate({
              userId: user.id,
              change: { role: event.target.value as AdminUser["role"] },
            })
          }
          className="rounded border border-line bg-page p-1 text-sm capitalize"
        >
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
      </td>
      <td className="py-3">
        <button
          type="button"
          disabled={locked}
          onClick={() => change.mutate({ userId: user.id, change: { is_active: !user.is_active } })}
          className={`h-8 rounded-full px-3 text-sm font-medium disabled:opacity-40 ${
            user.is_active ? "text-danger hover:bg-danger-soft" : "text-accent hover:bg-accent-soft"
          }`}
        >
          {user.is_active ? "Disable" : "Enable"}
        </button>
        {!user.is_active && <p className="text-xs text-ink-muted">Disabled</p>}
      </td>
    </tr>
  );
}

function Users({ q, me }: { q: string; me: string }) {
  const users = useAdminUsers(q);
  if (users.isPending) return <div aria-busy="true" className="h-40" />;
  if (!users.data) {
    return (
      <p role="alert" className="py-8 text-sm text-danger">
        Couldn't load users.
      </p>
    );
  }
  const items = users.data.pages.flatMap((page) => page.items);
  if (items.length === 0) return <p className="py-8 text-ink-muted">No users match.</p>;
  return (
    <>
      <table className="w-full text-left">
        <thead className="text-xs text-ink-muted">
          <tr>
            <th className="pb-2 font-medium">User</th>
            <th className="pb-2 font-medium">Role</th>
            <th className="pb-2 font-medium">Account</th>
          </tr>
        </thead>
        <tbody>
          {items.map((user) => (
            <Row key={user.id} user={user} self={user.username === me} />
          ))}
        </tbody>
      </table>
      <LoadMore pages={users} />
    </>
  );
}

export function AdminUsersPage() {
  const { user, isLoading } = useAuth();
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");

  if (isLoading) return null;
  if (user?.role !== "admin") return <NotFoundPage />;

  function search(event: FormEvent) {
    event.preventDefault();
    setQ(draft.trim());
  }

  return (
    <div className="mx-auto max-w-4xl px-4 pt-6 pb-10 sm:px-6">
      <h1 className="mb-1 text-2xl font-bold">Users</h1>
      <p className="mb-6 text-sm text-ink-muted">
        Change roles, and disable accounts: a disabled user is signed out everywhere and their
        videos leave every listing until they're enabled again.
      </p>
      <form onSubmit={search} role="search" className="mb-4 flex gap-2">
        <input
          type="search"
          aria-label="Search users"
          placeholder="Username or email"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={100}
          className="h-9 flex-1 rounded-full border border-line bg-page px-4 text-sm"
        />
        <button
          type="submit"
          className="h-9 rounded-full bg-hover px-4 text-sm font-medium hover:bg-hover-strong"
        >
          Search
        </button>
      </form>
      <Users q={q} me={user.username} />
    </div>
  );
}
