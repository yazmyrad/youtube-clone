import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { MAX_QUERY } from "../hooks/useSearch";
import { AccountIcon, Logo, MenuIcon, PlusIcon, SearchIcon } from "./icons";
import { UserMenu } from "./UserMenu";

export function Masthead({ onMenu }: { onMenu: () => void }) {
  const { pathname, search } = useLocation();
  const next = encodeURIComponent(pathname + search);
  const { user, isLoading, logout } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const current = pathname === "/results" ? (params.get("search_query") ?? "") : "";
  const [query, setQuery] = useState(current);

  // Show the search that is on screen, also after Back and Forward.
  useEffect(() => setQuery(current), [current]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (text) navigate(`/results?search_query=${encodeURIComponent(text)}`);
  }

  return (
    <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between gap-4 bg-page px-4">
      <div className="flex shrink-0 items-center gap-3">
        <button
          type="button"
          onClick={onMenu}
          aria-label="Guide"
          className="grid size-10 place-items-center rounded-full hover:bg-hover"
        >
          <MenuIcon />
        </button>
        <Link to="/" aria-label="Home">
          <Logo />
        </Link>
      </div>

      <form
        role="search"
        action="/results"
        onSubmit={submitSearch}
        className="hidden h-10 max-w-160 flex-1 sm:flex"
      >
        <input
          type="search"
          name="search_query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          maxLength={MAX_QUERY}
          placeholder="Search"
          aria-label="Search"
          className="min-w-0 flex-1 rounded-l-full border border-line px-4 outline-none focus:border-accent"
        />
        <button
          type="submit"
          aria-label="Search"
          className="grid w-16 place-items-center rounded-r-full border border-l-0 border-line bg-hover hover:bg-hover-strong"
        >
          <SearchIcon />
        </button>
      </form>

      <div className="flex shrink-0 items-center gap-3">
        {user && (
          <Link
            to="/upload"
            aria-label="Create"
            className="flex h-9 items-center gap-1 rounded-full bg-hover px-2 text-sm font-medium hover:bg-hover-strong sm:pr-4"
          >
            <PlusIcon />
            <span className="hidden sm:inline">Create</span>
          </Link>
        )}
        {user && <UserMenu user={user} onLogout={logout} />}
        {!user && !isLoading && (
          <Link
            to={`/login?next=${next}`}
            className="flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-sm font-medium text-accent hover:bg-accent-soft"
          >
            <AccountIcon />
            Sign in
          </Link>
        )}
      </div>
    </header>
  );
}
