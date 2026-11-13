import { VideoFeed } from "../components/VideoFeed";
import { useFeed } from "../hooks/useFeed";

export function HomePage() {
  return (
    <div className="px-4 pt-6 pb-10 sm:px-6">
      <VideoFeed
        query={useFeed()}
        heading={<h1 className="sr-only">Home</h1>}
        empty={
          <p className="p-16 text-center text-ink-muted">
            No videos yet. Be the first to upload one.
          </p>
        }
      />
    </div>
  );
}
