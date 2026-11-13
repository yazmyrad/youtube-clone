import { useState, type ComponentType } from "react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { useMySubscriptions, type SubscribedChannel } from "../hooks/useSubscriptions";
import { channelPath } from "./format";
import { HomeIcon, SubscriptionsIcon } from "./icons";

interface Entry {
  to: string;
  label: string;
  Icon: ComponentType;
}

const ENTRIES: Entry[] = [
  { to: "/", label: "Home", Icon: HomeIcon },
  { to: "/feed/subscriptions", label: "Subscriptions", Icon: SubscriptionsIcon },
];

/** How many channels the guide lists before "Show more", as on YouTube. */
export const COLLAPSED_CHANNELS = 7;

const ROW = "flex h-10 items-center gap-6 rounded-lg px-3 text-sm hover:bg-hover";
const activeRow = ({ isActive }: { isActive: boolean }) =>
  `${ROW} ${isActive ? "bg-hover font-medium" : ""}`;

function ChannelEntry({ channel }: { channel: SubscribedChannel }) {
  return (
    <NavLink to={channelPath(channel.username)} className={activeRow}>
      <span
        aria-hidden
        className="grid size-6 shrink-0 place-items-center rounded-full bg-accent text-xs font-medium text-white uppercase"
      >
        {Array.from(channel.display_name)[0] ?? "?"}
      </span>
      <span className="truncate">{channel.display_name}</span>
    </NavLink>
  );
}

/** The signed-in account's channels. Nothing while loading or on error: it's a side list. */
function Subscriptions() {
  const channels = useMySubscriptions();
  const [expanded, setExpanded] = useState(false);
  const all = channels.data ?? [];
  if (all.length === 0) return null;
  const shown = expanded ? all : all.slice(0, COLLAPSED_CHANNELS);
  return (
    <section aria-labelledby="guide-subscriptions" className="mt-3 border-t border-line pt-3">
      <h2 id="guide-subscriptions" className="px-3 pb-1 font-medium">
        Subscriptions
      </h2>
      {shown.map((channel) => (
        <ChannelEntry key={channel.username} channel={channel} />
      ))}
      {all.length > COLLAPSED_CHANNELS && (
        <button type="button" onClick={() => setExpanded((value) => !value)} className={ROW}>
          {expanded ? "Show fewer" : `Show ${all.length - COLLAPSED_CHANNELS} more`}
        </button>
      )}
    </section>
  );
}

/** The full guide: on wide screens, and inside the drawer. */
export function FullGuide() {
  const { user } = useAuth();
  return (
    <nav aria-label="Guide" className="flex flex-col p-3">
      {ENTRIES.map(({ to, label, Icon }) => (
        <NavLink key={to} to={to} end className={activeRow}>
          <Icon />
          {label}
        </NavLink>
      ))}
      {user && <Subscriptions />}
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
