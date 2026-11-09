import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";

import { FullGuide, MiniGuide } from "./Guide";
import { Logo, MenuIcon } from "./icons";
import { Masthead } from "./Masthead";

const WIDE = "(min-width: 1312px)";

export function Layout() {
  const [expanded, setExpanded] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => setDrawerOpen(false), [pathname]);

  useEffect(() => {
    if (!drawerOpen) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [drawerOpen]);

  const toggleGuide = () => {
    if (window.matchMedia(WIDE).matches) setExpanded((value) => !value);
    else setDrawerOpen((value) => !value);
  };

  return (
    <>
      <Masthead onMenu={toggleGuide} />

      <aside
        className={`fixed top-14 bottom-0 left-0 hidden w-18 guide:block ${expanded ? "wide:hidden" : ""}`}
      >
        <MiniGuide />
      </aside>
      {expanded && (
        <aside className="fixed top-14 bottom-0 left-0 hidden w-60 overflow-y-auto wide:block">
          <FullGuide />
        </aside>
      )}

      {drawerOpen && (
        <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label="Guide">
          <button
            type="button"
            aria-label="Close guide"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-black/50"
          />
          <div className="absolute inset-y-0 left-0 w-60 bg-page">
            <div className="flex h-14 items-center gap-3 px-4">
              <button
                type="button"
                aria-label="Close guide"
                onClick={() => setDrawerOpen(false)}
                className="grid size-10 place-items-center rounded-full hover:bg-hover"
              >
                <MenuIcon />
              </button>
              <Link to="/" aria-label="Home">
                <Logo />
              </Link>
            </div>
            <FullGuide />
          </div>
        </div>
      )}

      <main className={`pt-14 guide:pl-18 ${expanded ? "wide:pl-60" : ""}`}>
        <Outlet />
      </main>
    </>
  );
}
