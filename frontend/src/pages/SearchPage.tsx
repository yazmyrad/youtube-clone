import { useSearchParams } from "react-router-dom";

import { LoadMore } from "../components/LoadMore";
import { VideoRowCard } from "../components/VideoCard";
import { useRenewThumbnails } from "../hooks/useRenewThumbnails";
import { MIN_QUERY, searchText, useSearch } from "../hooks/useSearch";

function Notice({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 p-16 text-center">
      <p className="text-lg font-medium">{title}</p>
      {hint && <p className="text-ink-muted">{hint}</p>}
    </div>
  );
}

export function SearchPage() {
  const [params] = useSearchParams();
  const text = searchText(params.get("search_query"));
  const results = useSearch(text);
  const renewThumbnails = useRenewThumbnails(results);

  if (text === null) {
    return (
      <Notice
        title="Search for videos"
        hint={`Type at least ${MIN_QUERY} characters of a title.`}
      />
    );
  }
  if (results.isPending) {
    return (
      <p role="status" className="p-16 text-center text-ink-muted">
        Searching…
      </p>
    );
  }
  if (!results.data) {
    return (
      <div role="alert">
        <Notice title="Couldn't search right now" hint="Check your connection and try again." />
      </div>
    );
  }

  const videos = results.data.pages.flatMap((page) => page.items);
  if (videos.length === 0) {
    return <Notice title="No results found" hint="Try different keywords." />;
  }

  return (
    <div className="mx-auto max-w-280 px-4 pt-6 pb-10 sm:px-6">
      <h1 className="sr-only">Search results for {text}</h1>
      <ul className="flex flex-col gap-4">
        {videos.map((video) => (
          <li key={video.id}>
            <VideoRowCard video={video} onThumbnailError={renewThumbnails} />
          </li>
        ))}
      </ul>
      <LoadMore pages={results} />
    </div>
  );
}
