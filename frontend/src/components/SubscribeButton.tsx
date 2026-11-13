import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { useSubscription, type Channel } from "../hooks/useChannel";

/** YouTube's pill: dark "Subscribe", grey "Subscribed". Hidden on your own channel. */
export function SubscribeButton({ channel }: { channel: Channel }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const subscription = useSubscription(channel.username);

  if (user?.username === channel.username) return null;

  function press() {
    if (!user) {
      void navigate(`/login?next=${encodeURIComponent(pathname + search)}`);
      return;
    }
    subscription.mutate(!channel.is_subscribed);
  }

  return (
    <div className="flex shrink-0 flex-col items-start gap-1">
      <button
        type="button"
        aria-pressed={channel.is_subscribed}
        disabled={subscription.isPending}
        onClick={press}
        className={`h-9 rounded-full px-4 text-sm font-medium disabled:opacity-60 ${
          channel.is_subscribed
            ? "bg-hover hover:bg-hover-strong"
            : "bg-ink text-page hover:opacity-85"
        }`}
      >
        {channel.is_subscribed ? "Subscribed" : "Subscribe"}
      </button>
      {subscription.isError && (
        <p role="alert" className="text-xs text-red-700">
          {subscription.error.message}
        </p>
      )}
    </div>
  );
}
