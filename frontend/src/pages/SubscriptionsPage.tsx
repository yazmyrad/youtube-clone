import { Link, useLocation } from "react-router-dom";

import { VideoFeed } from "../components/VideoFeed";
import { SubscriptionsIcon } from "../components/icons";
import { useAuth } from "../hooks/useAuth";
import { useSubscriptionFeed } from "../hooks/useSubscriptions";

function SignedOut() {
  const { pathname } = useLocation();
  return (
    <div className="flex flex-col items-center gap-4 p-16 text-center">
      <span className="text-ink-muted [&_svg]:size-24">
        <SubscriptionsIcon />
      </span>
      <h1 className="text-2xl">Don't miss new videos</h1>
      <p className="text-sm text-ink-muted">
        Sign in to see updates from the channels you subscribe to
      </p>
      <Link
        to={`/login?next=${encodeURIComponent(pathname)}`}
        className="rounded-full border border-line px-4 py-2 text-sm font-medium text-accent hover:bg-accent-soft"
      >
        Sign in
      </Link>
    </div>
  );
}

function Feed() {
  return (
    <VideoFeed
      query={useSubscriptionFeed()}
      heading={<h1 className="mb-4 text-xl font-bold">Latest</h1>}
      empty={
        <div className="p-16 text-center">
          <h1 className="text-xl font-medium">No videos from your subscriptions yet</h1>
          <p className="mt-2 text-ink-muted">
            Subscribe to channels and their new videos will show up here.
          </p>
        </div>
      }
    />
  );
}

export function SubscriptionsPage() {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;
  return <div className="px-4 pt-6 pb-10 sm:px-6">{user ? <Feed /> : <SignedOut />}</div>;
}
