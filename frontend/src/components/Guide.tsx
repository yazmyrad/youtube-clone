import type { ComponentType } from "react";
import { NavLink } from "react-router-dom";

import { HomeIcon } from "./icons";

interface Entry {
  to: string;
  label: string;
  Icon: ComponentType;
}

const ENTRIES: Entry[] = [{ to: "/", label: "Home", Icon: HomeIcon }];

/** The full guide: on wide screens, and inside the drawer. */
export function FullGuide() {
  return (
    <nav aria-label="Guide" className="flex flex-col p-3">
      {ENTRIES.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          end
          className={({ isActive }) =>
            `flex h-10 items-center gap-6 rounded-lg px-3 text-sm hover:bg-hover ${isActive ? "bg-hover font-medium" : ""}`
          }
        >
          <Icon />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

export function MiniGuide() {
  return (
    <nav aria-label="Guide" className="flex flex-col px-1">
      {ENTRIES.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          end
          className="flex h-18 flex-col items-center justify-center gap-1.5 rounded-lg text-[10px] hover:bg-hover"
        >
          <Icon />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
