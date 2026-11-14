import { Link } from "react-router-dom";

import { useRenewThumbnails } from "../hooks/useRenewThumbnails";
import { useShortsFeed } from "../hooks/useShorts";
import { ShortsIcon } from "./icons";
import { ShortCard } from "./ShortCard";

/** How many Shorts the home shelf shows, as YouTube does on a wide screen. */
export const SHELF_SIZE = 6;

/** The home page's Shorts shelf. Nothing at all while loading, on error or with no Shorts. */
export function ShortsShelf() {
  const shorts = useShortsFeed();
  const renewThumbnails = useRenewThumbnails(shorts);
  const items = (shorts.data?.pages[0]?.items ?? []).slice(0, SHELF_SIZE);
  if (items.length === 0) return null;
  return (
    <section aria-labelledby="shorts-shelf" className="border-y border-line py-6">
      <h2 id="shorts-shelf" className="mb-4 flex items-center gap-2 text-xl font-bold">
        <span className="text-brand">
          <ShortsIcon />
        </span>
        <Link to="/shorts">Shorts</Link>
      </h2>
      <div className="grid auto-cols-[minmax(9.5rem,1fr)] grid-flow-col gap-4 overflow-x-auto pb-1">
        {items.map((video) => (
          <ShortCard key={video.id} video={video} onThumbnailError={renewThumbnails} />
        ))}
      </div>
    </section>
  );
}
