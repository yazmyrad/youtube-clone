import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center gap-4 p-16 text-center">
      <h1 className="text-xl font-medium">This page isn't available</h1>
      <p className="text-ink-muted">The link may be broken, or the page may have been removed.</p>
      <Link to="/" className="rounded-full bg-hover px-4 py-2 text-sm font-medium hover:bg-hover-strong">
        Go to home
      </Link>
    </div>
  );
}
