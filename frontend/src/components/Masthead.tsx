import { Link, useLocation } from "react-router-dom";

import { AccountIcon, Logo, MenuIcon, SearchIcon } from "./icons";

export function Masthead({ onMenu }: { onMenu: () => void }) {
  const { pathname, search } = useLocation();
  const next = encodeURIComponent(pathname + search);

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

      {/* Search results arrive in step 17. */}
      <form
        role="search"
        onSubmit={(event) => event.preventDefault()}
        className="hidden h-10 max-w-160 flex-1 sm:flex"
      >
        <input
          type="search"
          name="search_query"
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

      <div className="flex shrink-0 items-center">
        <Link
          to={`/login?next=${next}`}
          className="flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-sm font-medium text-accent hover:bg-accent-soft"
        >
          <AccountIcon />
          Sign in
        </Link>
      </div>
    </header>
  );
}
